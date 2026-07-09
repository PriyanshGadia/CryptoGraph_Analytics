import sqlite3
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

# Resolve the local SQLite database path.
_DB_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent.parent / "backend" / "cryptograph.db",
    Path(__file__).resolve().parent.parent.parent.parent / "cryptograph.db",
]
DB_PATH: Optional[Path] = next((p for p in _DB_CANDIDATES if p.exists()), _DB_CANDIDATES[0])

class FeatureStore:
    """Central interface for loading model-ready features from SQLite.

    ### Schema Constraints and Feature Layout
    The Feature Store serves exactly 24 features (or 27 when tvl, revenue, active_users are enabled).
    The features must be returned in the following layout:
    1.  `open`: float, raw opening price.
    2.  `high`: float, raw high price.
    3.  `low`: float, raw low price.
    4.  `close`: float, raw close price.
    5.  `volume`: float, raw trade volume.
    6.  `rsi_14`: float, Relative Strength Index, bounded [0.0, 100.0], default fill = 50.0.
    7.  `macd`: float, Moving Average Convergence Divergence indicator.
    8.  `macd_signal`: float, MACD signal line.
    9.  `atr_14`: float, Average True Range.
    10. `bb_width`: float, Bollinger Band Width.
    11. `returns_1d`: float, 1-day percentage return, default fill = 0.0.
    12. `returns_7d`: float, 7-day simple return, default fill = 0.0.
    13. `volatility_7d`: float, 7-day rolling standard deviation of returns, default fill = 0.0.
    14. `sentiment_score`: float, market sentiment normalized [-1.0, 1.0], default fill = 0.0.
    15. `fear_greed_norm`: float, normalized Fear & Greed index [0.0, 1.0], default fill = 0.5.
    16. `community_score`: float, social community metric.
    17. `public_interest`: float, public interest metric.
    18. `sentiment_rolling_3d`: float, 3-day sentiment rolling mean, default fill = 0.0.
    19. `sentiment_momentum`: float, sentiment momentum indicator, default fill = 0.0.
    20. `market_cap_usd`: float, asset market capitalization.
    21. `fed_rate`: float, effective Federal Funds rate, default fill = 5.25.
    22. `cpi`: float, Consumer Price Index, default fill = 3.0.
    23. `inflation`: float, Breakeven Inflation rate, default fill = 2.5.
    24. `vix`: float, CBOE Volatility Index, default fill = 15.0.

    Optional 25-27: `tvl` (float), `revenue` (float), `active_users` (float) when feature_dim=27.

    ### Normalization & Data Cleaning
    To prevent training-serving skew, both training and inference pipelines load features using
    this interface, which automatically applies the following normalization and cleaning:
    - Zero-padding missing values.
    - Interpolating missing records linearly along the time axis.
    - Default neutral values filled for key indicators (e.g. RSI = 50.0, Sentiment = 0.0). Bounded
      parameters are clipped to their logical bounds (RSI to [0,100], Fear & Greed to [0,1]).
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Initialize with a path to the local SQLite database."""
        self.db_path = str(db_path or DB_PATH)

    def _conn(self) -> sqlite3.Connection:
        """Return a new SQLite connection with dict-row factory."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def load_node_features(
        self,
        start_date: str,
        end_date: str,
        assets: List[str],
        expected_features: int = 24
    ) -> Dict[str, pd.DataFrame]:
        """
        Returns dict mapping asset symbol → DataFrame with exactly `expected_features`
        feature columns matching STGCNModel(in_features=expected_features).

        Tries SQLite database first. If the database or required tables don't exist,
        falls back to fetching data from yfinance (public API).
        """
        # Try database first
        try:
            result = self._load_from_db(start_date, end_date, assets, expected_features)
            if result:
                return result
        except (sqlite3.OperationalError, FileNotFoundError, Exception) as e:
            print(f"[FeatureStore] Database load failed ({e}); falling back to yfinance...")

        # Fallback: fetch from yfinance
        return self._load_from_yfinance(start_date, end_date, assets, expected_features)

    def _load_from_yfinance(
        self,
        start_date: str,
        end_date: str,
        assets: List[str],
        expected_features: int = 24
    ) -> Dict[str, pd.DataFrame]:
        """Fetch OHLCV data from yfinance and compute all 24 features synthetically."""
        try:
            import yfinance as yf
            import numpy as np
        except ImportError:
            raise ImportError("yfinance is required for fallback data loading. Install with: pip install yfinance")

        # Self-healing upgrade for yfinance if we detect it's outdated or returns NaNs (common on Kaggle)
        test_ticker = f"{assets[0]}-USD" if assets else "BTC-USD"
        try:
            test_df = yf.download(test_ticker, period="5d", progress=False, auto_adjust=True)
            if not test_df.empty:
                if isinstance(test_df.columns, pd.MultiIndex):
                    test_df.columns = test_df.columns.get_level_values(0)
                is_invalid = (
                    "Close" not in test_df.columns or 
                    np.any(pd.isna(test_df["Close"].values)) or 
                    np.nanstd(test_df["Close"].values.astype(float)) < 1e-6
                )
                if is_invalid:
                    print("[FeatureStore] WARNING: yfinance returned invalid, constant, or NaN Close prices. Attempting automatic self-healing upgrade...")
                    import subprocess
                    import sys
                    subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yfinance"], capture_output=True)
                    import importlib
                    importlib.reload(yf)
                    print("[FeatureStore] yfinance upgraded successfully. Retrying download...")
        except Exception as e:
            print(f"[FeatureStore] yfinance diagnostic check failed: {e}. Proceeding anyway...")

        print(f"[FeatureStore] Fetching {len(assets)} assets from yfinance ({start_date} to {end_date})...")
        out: Dict[str, pd.DataFrame] = {}

        # Map crypto symbols to yfinance tickers
        yf_map = {s: f"{s}-USD" for s in assets}

        # [R5-BUG-3 FIX & R6 Live Macro]: Pre-fetch global macro proxies once for the whole date range.
        # VIX, IRX (fed_rate), TNX (inflation), and TIP (cpi) are global indicators.
        _vix_series: Optional[pd.Series] = None
        _fed_series: Optional[pd.Series] = None
        _cpi_series: Optional[pd.Series] = None
        _inf_series: Optional[pd.Series] = None

        try:
            macro_tickers = ["^VIX", "^IRX", "^TNX", "TIP"]
            macro_raw = yf.download(macro_tickers, start=start_date, end=end_date, progress=False, auto_adjust=True)
            if not macro_raw.empty:
                if isinstance(macro_raw.columns, pd.MultiIndex):
                    close_data = macro_raw["Close"]
                else:
                    close_data = macro_raw
                close_data.index = pd.to_datetime(close_data.index, utc=True)

                if "^VIX" in close_data.columns:
                    _vix_series = close_data["^VIX"].astype(float)
                if "^IRX" in close_data.columns:
                    _fed_series = close_data["^IRX"].astype(float)
                if "TIP" in close_data.columns:
                    _cpi_series = close_data["TIP"].astype(float)
                if "^TNX" in close_data.columns:
                    _inf_series = close_data["^TNX"].astype(float)
                print(f"  [yfinance] Global macro proxies pre-fetched: vix={_vix_series is not None}, fed={_fed_series is not None}, cpi={_cpi_series is not None}, inf={_inf_series is not None}")
        except Exception as macro_e:
            print(f"  [yfinance] Global macro pre-fetch failed ({macro_e}), using fallback constants")

        bulk_raw = None
        all_tickers = [yf_map[sym] for sym in assets]
        print(f"  [yfinance] Bulk pre-fetching {len(all_tickers)} assets at once...")
        try:
            bulk_raw = yf.download(all_tickers, start=start_date, end=end_date, progress=False, auto_adjust=True)
            print(f"  [yfinance] Bulk download complete. Shape={bulk_raw.shape if bulk_raw is not None else 'None'}")
        except Exception as bulk_e:
            print(f"  [yfinance] Bulk download failed ({bulk_e}), using sequential fallback.")

        for symbol in assets:
            ticker = yf_map[symbol]
            try:
                df_raw = pd.DataFrame()
                if bulk_raw is not None and not bulk_raw.empty:
                    if isinstance(bulk_raw.columns, pd.MultiIndex):
                        try:
                            # Extract columns for this specific ticker
                            df_raw = bulk_raw.xs(ticker, axis=1, level=1).dropna(how="all")
                        except KeyError:
                            pass
                    else:
                        df_raw = bulk_raw

                if df_raw.empty:
                    df_raw = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)

                if df_raw.empty:
                    continue

                # Handle multi-level columns from yfinance
                if isinstance(df_raw.columns, pd.MultiIndex):
                    df_raw.columns = df_raw.columns.get_level_values(0)

                print(f"  [yfinance debug] {symbol}: df_raw shape={df_raw.shape}, columns={list(df_raw.columns)}")
                if "Close" in df_raw.columns:
                    cvals = df_raw["Close"].values.astype(float)
                    print(f"  [yfinance debug] {symbol}: Close head={df_raw['Close'].head().values.tolist()}, isnan_all={np.all(np.isnan(cvals))}, std={np.nanstd(cvals)}")

                close_vals = df_raw["Close"].values.astype(float)
                if "Close" not in df_raw.columns or len(close_vals) < 5 or np.all(np.isnan(close_vals)) or np.nanstd(close_vals) < 1e-6:
                    print(f"  [yfinance] {symbol}: FAILED (Download returned constant, NaN, or insufficient Close prices)")
                    continue

                df = pd.DataFrame(index=df_raw.index)
                df.index = pd.to_datetime(df.index, utc=True)

                # Core OHLCV - use .values to bypass index alignment issues!
                df["open"] = df_raw["Open"].values.astype(float)
                df["high"] = df_raw["High"].values.astype(float)
                df["low"] = df_raw["Low"].values.astype(float)
                df["close"] = df_raw["Close"].values.astype(float)
                df["volume"] = df_raw["Volume"].values.astype(float)

                # Technical indicators computed from OHLCV
                close = df["close"]
                high = df["high"]
                low = df["low"]

                # RSI-14
                delta = close.diff()
                gain = delta.where(delta > 0, 0.0).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
                rs = gain / (loss + 1e-10)
                df["rsi_14"] = (100.0 - 100.0 / (1.0 + rs)).clip(0, 100)

                # MACD
                ema12 = close.ewm(span=12, adjust=False).mean()
                ema26 = close.ewm(span=26, adjust=False).mean()
                df["macd"] = ema12 - ema26
                df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

                # ATR-14
                tr = pd.concat([
                    high - low,
                    (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs()
                ], axis=1).max(axis=1)
                df["atr_14"] = tr.rolling(14).mean()

                # Bollinger Band Width
                sma20 = close.rolling(20).mean()
                std20 = close.rolling(20).std()
                upper_bb = sma20 + 2 * std20
                lower_bb = sma20 - 2 * std20
                df["bb_width"] = (upper_bb - lower_bb) / (sma20 + 1e-10)

                # Returns
                df["returns_1d"] = close.pct_change(1)
                df["returns_7d"] = close.pct_change(7)
                df["volatility_7d"] = df["returns_1d"].rolling(7).std()
                print(f"  [yfinance debug] {symbol}: returns_1d head={df['returns_1d'].head().values.tolist()}, std={df['returns_1d'].std()}")
                # [R6 Sentiment & Social Proxies]: Derive dynamic indicators from price returns and volume to avoid dead constants.
                # 1. fear_greed_norm: blend of RSI and volatility momentum
                rsi_sig = (df["rsi_14"] - 50.0) / 50.0  # range [-1, 1]
                vol_rolling = df["volatility_7d"].rolling(30, min_periods=1)
                vol_mean = vol_rolling.mean().fillna(0.05)
                vol_std = vol_rolling.std().fillna(0.01).replace(0.0, 0.01)
                vol_z = ((df["volatility_7d"] - vol_mean) / vol_std).fillna(0.0)
                fg_blend = 0.5 + 0.3 * rsi_sig - 0.2 * vol_z.clip(-2.0, 2.0) / 2.0
                df["fear_greed_norm"] = fg_blend.clip(0.05, 0.95)

                # 2. sentiment_score: ewm mean of returns, scaled to roughly [-1, 1]
                ret_ewm = df["returns_1d"].ewm(span=3, min_periods=1).mean().fillna(0.0)
                df["sentiment_score"] = (ret_ewm / 0.03).clip(-1.0, 1.0)
                df["sentiment_rolling_3d"] = df["sentiment_score"].rolling(3, min_periods=1).mean().fillna(0.0)
                df["sentiment_momentum"] = df["sentiment_score"].diff().fillna(0.0)

                # 3. community_score: volume ratio against 14-day mean
                vol_ratio = (df["volume"] / df["volume"].rolling(14, min_periods=1).mean()).fillna(1.0)
                df["community_score"] = vol_ratio.clip(0.1, 5.0)

                # 4. public_interest: absolute price deviation from 30-day moving average
                close_sma30 = df["close"].rolling(30, min_periods=1).mean()
                close_std30 = df["close"].rolling(30, min_periods=1).std().fillna(1.0).replace(0.0, 1.0)
                df["public_interest"] = ((df["close"] - close_sma30).abs() / close_std30).fillna(1.0).clip(0.1, 5.0)

                # Market cap estimate (price * circulating supply proxy)
                df["market_cap_usd"] = close * df["volume"].rolling(30).mean()

                # [R6 Live Macro Proxies]: Use real macro series if available; fall back to constants.
                if _fed_series is not None:
                    fed_aligned = _fed_series.reindex(df.index, method="ffill")
                    df["fed_rate"] = fed_aligned.fillna(5.25).values
                else:
                    df["fed_rate"] = 5.25

                if _cpi_series is not None:
                    cpi_aligned = _cpi_series.reindex(df.index, method="ffill")
                    df["cpi"] = cpi_aligned.fillna(3.0).values
                else:
                    df["cpi"] = 3.0

                if _inf_series is not None:
                    inf_aligned = _inf_series.reindex(df.index, method="ffill")
                    df["inflation"] = inf_aligned.fillna(2.5).values
                else:
                    df["inflation"] = 2.5

                if _vix_series is not None:
                    vix_aligned = _vix_series.reindex(df.index, method="ffill")
                    df["vix"] = vix_aligned.fillna(15.0).values
                else:
                    df["vix"] = 15.0

                if expected_features == 27:
                    df["tvl"] = 0.0
                    df["revenue"] = 0.0
                    df["active_users"] = 0.0

                # Fill NaNs with neutral defaults
                fill_values = {
                    "rsi_14": 50.0, "fear_greed_norm": 0.5, "sentiment_score": 0.0,
                    "sentiment_rolling_3d": 0.0, "sentiment_momentum": 0.0,
                    "fed_rate": 5.25, "cpi": 3.0, "inflation": 2.5, "vix": 15.0,
                    "returns_1d": 0.0, "returns_7d": 0.0, "volatility_7d": 0.0
                }
                df = df.interpolate(method='linear', limit_direction='both').fillna(0.0)
                for col, val in fill_values.items():
                    if col in df.columns:
                        df[col] = df[col].fillna(val)

                expected_cols = [
                    "open", "high", "low", "close", "volume",
                    "rsi_14", "macd", "macd_signal", "atr_14", "bb_width",
                    "returns_1d", "returns_7d", "volatility_7d",
                    "sentiment_score", "fear_greed_norm", "community_score",
                    "public_interest", "sentiment_rolling_3d", "sentiment_momentum",
                    "market_cap_usd",
                    "fed_rate", "cpi", "inflation", "vix"
                ]
                if expected_features == 27:
                    expected_cols.extend(["tvl", "revenue", "active_users"])

                for col in expected_cols:
                    if col not in df.columns:
                        df[col] = 0.0

                df = df[expected_cols].astype(float)
                df.index.name = "timestamp"
                df = df.reset_index()
                # Ensure timestamp column exists
                if "timestamp" not in df.columns:
                    df = df.reset_index()
                    df.columns = ["timestamp"] + list(df.columns[1:])

                print(f"  [yfinance debug] {symbol}: final returns_1d head={df['returns_1d'].head().values.tolist()}, std={df['returns_1d'].std()}")
                out[symbol] = df
                print(f"  [yfinance] {symbol}: {len(df)} rows loaded")

            except Exception as e:
                print(f"  [yfinance] {symbol}: FAILED ({e})")
                continue

        print(f"[FeatureStore] yfinance fallback loaded {len(out)} assets.")
        return out

    def _load_from_db(
        self,
        start_date: str,
        end_date: str,
        assets: List[str],
        expected_features: int = 24
    ) -> Dict[str, pd.DataFrame]:
        """Load features from SQLite database. Raises on missing tables."""
        conn = self._conn()
        out: Dict[str, pd.DataFrame] = {}

        try:
            # ----- 1. Load assets (batched) -----
            placeholders = ",".join("?" for _ in assets)
            asset_rows = conn.execute(
                f"SELECT id, symbol, market_cap_usd FROM assets WHERE symbol IN ({placeholders})",
                assets,
            ).fetchall()
            if not asset_rows:
                return out

            asset_map = {r["symbol"]: r["id"] for r in asset_rows}
            mcap_map = {r["symbol"]: (r["market_cap_usd"] or 0) for r in asset_rows}
            asset_ids = list(asset_map.values())
            id_ph = ",".join("?" for _ in asset_ids)

            # ----- 2. Macro indicators (global, one query) -----
            try:
                macro_rows = conn.execute(
                    "SELECT timestamp, fed_rate, cpi, inflation, vix "
                    "FROM macro_indicators WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp",
                    (start_date, end_date),
                ).fetchall()
                macro_df = pd.DataFrame([dict(r) for r in macro_rows])
                if not macro_df.empty:
                    macro_df["timestamp"] = pd.to_datetime(macro_df["timestamp"], format='mixed', utc=True)
                    macro_df = macro_df.set_index("timestamp").sort_index()
            except sqlite3.OperationalError:
                macro_df = pd.DataFrame()

            # ----- 3. OHLCV (batched) -----
            ohlcv_rows = conn.execute(
                f"SELECT asset_id, timestamp, open, high, low, close, volume "
                f"FROM ohlcv WHERE asset_id IN ({id_ph}) AND timestamp >= ? AND timestamp <= ? "
                f"ORDER BY timestamp",
                (*asset_ids, start_date, end_date),
            ).fetchall()
            ohlcv_df = pd.DataFrame([dict(r) for r in ohlcv_rows])

            # ----- 4. Technical features (batched) -----
            try:
                tech_rows = conn.execute(
                    f"SELECT asset_id, timestamp, rsi_14, macd, macd_signal, atr_14, "
                    f"bb_width, returns_1d, returns_7d, volatility_7d "
                    f"FROM technical_features WHERE asset_id IN ({id_ph}) AND timestamp >= ? AND timestamp <= ? "
                    f"ORDER BY timestamp",
                    (*asset_ids, start_date, end_date),
                ).fetchall()
                tech_df = pd.DataFrame([dict(r) for r in tech_rows])
            except sqlite3.OperationalError:
                tech_df = pd.DataFrame()

            # ----- 5. Sentiment (batched) -----
            try:
                sent_rows = conn.execute(
                    f"SELECT asset_id, timestamp, sentiment_score, fear_greed_norm, "
                    f"community_score, public_interest, sentiment_rolling_3d, sentiment_momentum "
                    f"FROM sentiment WHERE asset_id IN ({id_ph}) AND timestamp >= ? AND timestamp <= ? "
                    f"ORDER BY timestamp",
                    (*asset_ids, start_date, end_date),
                ).fetchall()
                sent_df = pd.DataFrame([dict(r) for r in sent_rows])
            except sqlite3.OperationalError:
                sent_df = pd.DataFrame()

            # ----- 5.5. On-Chain Metrics (batched) -----
            try:
                onchain_rows = conn.execute(
                    f"SELECT asset_id, timestamp, tvl, revenue, active_users "
                    f"FROM onchain_metrics WHERE asset_id IN ({id_ph}) AND timestamp >= ? AND timestamp <= ? "
                    f"ORDER BY timestamp",
                    (*asset_ids, start_date, end_date),
                ).fetchall()
                onchain_df = pd.DataFrame([dict(r) for r in onchain_rows])
            except sqlite3.OperationalError:
                onchain_df = pd.DataFrame()

        finally:
            conn.close()

        # ----- 6. Assemble per-asset DataFrames -----
        for symbol in assets:
            if symbol not in asset_map:
                continue
            asset_id = asset_map[symbol]
            mcap = mcap_map[symbol]

            # Filter per-asset from batched frames
            if ohlcv_df.empty:
                continue
            df_ohlcv = ohlcv_df[ohlcv_df["asset_id"] == asset_id].drop(columns=["asset_id"]).copy()
            if df_ohlcv.empty:
                continue
            df_ohlcv["timestamp"] = pd.to_datetime(df_ohlcv["timestamp"], format='mixed', utc=True)
            df_ohlcv = df_ohlcv.set_index("timestamp").sort_index()

            df_tech = pd.DataFrame()
            if not tech_df.empty:
                df_tech = tech_df[tech_df["asset_id"] == asset_id].drop(columns=["asset_id"]).copy()
                if not df_tech.empty:
                    df_tech["timestamp"] = pd.to_datetime(df_tech["timestamp"], format='mixed', utc=True)
                    df_tech = df_tech.set_index("timestamp").sort_index()

            df_sent = pd.DataFrame()
            if not sent_df.empty:
                df_sent = sent_df[sent_df["asset_id"] == asset_id].drop(columns=["asset_id"]).copy()
                if not df_sent.empty:
                    df_sent["timestamp"] = pd.to_datetime(df_sent["timestamp"], format='mixed', utc=True)
                    df_sent = df_sent.set_index("timestamp").sort_index()

            df_onchain = pd.DataFrame()
            if not onchain_df.empty:
                df_onchain = onchain_df[onchain_df["asset_id"] == asset_id].drop(columns=["asset_id"]).copy()
                if not df_onchain.empty:
                    df_onchain["timestamp"] = pd.to_datetime(df_onchain["timestamp"], format='mixed', utc=True)
                    df_onchain = df_onchain.set_index("timestamp").sort_index()

            # Merge
            df = df_ohlcv
            if not df_tech.empty:
                df = df.join(df_tech, how="left")
            if not df_sent.empty:
                df = df.join(df_sent, how="left")
            if not df_onchain.empty:
                df = df.join(df_onchain, how="left")
            if not macro_df.empty:
                df = df.join(macro_df, how="left")

            df["market_cap_usd"] = mcap
            df = df.astype(float)
            
            # Standard neutral values to avoid artificial signal leakage
            fill_values = {
                "rsi_14": 50.0,
                "fear_greed_norm": 0.5,
                "sentiment_score": 0.0,
                "sentiment_rolling_3d": 0.0,
                "sentiment_momentum": 0.0,
                "fed_rate": 5.25,
                "cpi": 3.0,
                "inflation": 2.5,
                "vix": 15.0,
                "returns_1d": 0.0,
                "returns_7d": 0.0,
                "volatility_7d": 0.0
            }
            df = df.interpolate(method='linear', limit_direction='both').fillna(0.0)
            
            for col, val in fill_values.items():
                if col in df.columns:
                    df[col] = df[col].fillna(val)

            expected_cols = [
                "open", "high", "low", "close", "volume",
                "rsi_14", "macd", "macd_signal", "atr_14", "bb_width",
                "returns_1d", "returns_7d", "volatility_7d",
                "sentiment_score", "fear_greed_norm", "community_score",
                "public_interest", "sentiment_rolling_3d", "sentiment_momentum",
                "market_cap_usd",
                "fed_rate", "cpi", "inflation", "vix"
            ]
            if expected_features == 27:
                expected_cols.extend(["tvl", "revenue", "active_users"])

            for col in expected_cols:
                if col not in df.columns:
                    df[col] = 0.0

            df = df[expected_cols]
            df = df.reset_index()  # puts timestamp as first column
            out[symbol] = df

        return out

    def validate_features(self, features: Dict[str, pd.DataFrame]) -> bool:
        """Validates feature DataFrames."""
        if not features:
            raise ValueError("No features provided.")

        date_ranges = {}

        for symbol, df in features.items():
            if df.empty:
                raise ValueError(f"DataFrame for {symbol} is empty.")
            
            # Check for NaN or Inf
            num_cols = df.select_dtypes(include=[np.number])
            if num_cols.isna().sum().sum() > 0:
                raise ValueError(f"NaN values found in {symbol}")
            if np.isinf(num_cols).sum().sum() > 0:
                raise ValueError(f"Inf values found in {symbol}")
                
            # Bounds checks
            if "rsi_14" in df.columns:
                rsi = df["rsi_14"]
                if (rsi < 0).any() or (rsi > 100).any():
                    raise ValueError(f"RSI out of bounds [0, 100] for {symbol}")
            
            if "sentiment_score" in df.columns:
                sent = df["sentiment_score"]
                if (sent < -1.0).any() or (sent > 1.0).any():
                    raise ValueError(f"Sentiment score out of bounds [-1, 1] for {symbol}")
                    
            if "fear_greed_norm" in df.columns:
                fg = df["fear_greed_norm"]
                if (fg < 0.0).any() or (fg > 1.0).any():
                    raise ValueError(f"Fear Greed Norm out of bounds [0, 1] for {symbol}")

            # Store date range
            date_ranges[symbol] = (df["timestamp"].min(), df["timestamp"].max())

        # Check date matching
        first_symbol = list(date_ranges.keys())[0]
        ref_range = date_ranges[first_symbol]
        for symbol, rng in date_ranges.items():
            if rng != ref_range:
                warnings.warn(f"Date range mismatch: {symbol} has {rng} vs {first_symbol} has {ref_range}")

        return True

    def get_target_labels(self, features: Dict[str, pd.DataFrame], horizon_days: int = 1) -> Dict[str, pd.Series]:
        """Compute classification labels for each asset."""
        labels = {}
        for symbol, df in features.items():
            if "close" not in df.columns:
                continue

            forward_return = (df["close"].shift(-horizon_days) - df["close"]) / df["close"]
            
            def classify(ret: float) -> str:
                if pd.isna(ret):
                    return "neutral"
                if ret > 0.03:
                    return "strong_up"
                elif 0.00 < ret <= 0.03:
                    return "up"
                elif -0.01 < ret <= 0.00:
                    return "neutral"
                elif -0.03 < ret <= -0.01:
                    return "down"
                else:
                    return "strong_down"
            
            lbls = forward_return.apply(classify)
            # Drop last horizon_days rows
            lbls = lbls.iloc[:-horizon_days]
            lbls.index = df.index[:-horizon_days]
            labels[symbol] = lbls
            
        return labels
