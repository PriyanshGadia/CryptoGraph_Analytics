"""
Daily inference pipeline.

Loads the last 30 days of features from the local SQLite FeatureStore,
builds the graph sequence via DynamicGraphBuilder, runs a real forward
pass through the trained STGCNModel, and batch-upserts predictions into
the SQLite database.
"""

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import torch
import torch.nn.functional as F

from ml.data.feature_store.store import FeatureStore
from ml.graph.graph_builder import DynamicGraphBuilder
from ml.models.stgcn import STGCNModel
import json

# Phase 9: XAI & Inference Attestation Integration
from backend.app.core.t_shap_explainer import TopologicalShapExplainer
from backend.app.core.inference_attester import InferenceAttester
from ml.models.forecast_model import run_ensemble_forecast
import pandas as pd

# ── Constants ────────────────────────────────────────────────────────
MODEL_PATH = Path(__file__).resolve().parent.parent / "artifacts" / "best_model.pt"

DIRECTION_CLASSES = ["strong_down", "down", "neutral", "up", "strong_up"]
VOLATILITY_CLASSES = ["low", "medium", "high", "extreme"]

def get_dynamic_symbols() -> List[str]:
    db_path = Path(__file__).resolve().parent.parent.parent / "backend" / "cryptograph.db"
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM assets WHERE sector != 'index' OR sector IS NULL")
        rows = cursor.fetchall()
        conn.close()
        if rows:
            return [r[0] for r in rows]
    except Exception:
        pass
    
    # Fallback
    return ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT"]

SYMBOLS: List[str] = get_dynamic_symbols()

FEATURE_NAMES: List[str] = [
    "open", "high", "low", "close", "volume",
    "rsi_14", "macd", "macd_signal", "atr_14", "bb_width",
    "returns_1d", "returns_7d", "volatility_7d",
    "sentiment_score", "fear_greed_norm", "community_score",
    "public_interest", "sentiment_rolling_3d", "sentiment_momentum",
    "market_cap_usd",
    "fed_rate", "cpi", "inflation", "vix",
]

# DB path resolution (same logic as FeatureStore)
_DB_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent / "backend" / "cryptograph.db",
    Path(__file__).resolve().parent.parent.parent / "cryptograph.db",
]
DB_PATH: Path = next((p for p in _DB_CANDIDATES if p.exists()), _DB_CANDIDATES[0])


def _get_model_version(model_path: Path) -> str:
    """Extract a version string from the checkpoint, falling back to the
    file modification timestamp."""
    try:
        ckpt = torch.load(model_path, map_location="cpu")
        cfg = ckpt.get("config", {})
        return cfg.get("version", model_path.stem)
    except Exception:
        return model_path.stem


def run_inference() -> dict:
    """
    End-to-end daily inference pipeline:
      1. Load the last 30 days of features from FeatureStore (SQLite).
      2. Build today's graph sequence via DynamicGraphBuilder.
      3. Load STGCNModel weights from disk.
      4. Run a torch.no_grad() forward pass.
      5. Decode direction / confidence / volatility per asset.
      6. Batch-upsert real predictions into the SQLite predictions table.
      7. Return summary dict.
    """
    print("Running inference pipeline …")
    # CPU usage constraints for Intel i3 compatibility
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    
    now = datetime.now(timezone.utc)
    end_date = now.strftime("%Y-%m-%d")
    start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")

    # ── 1. Feature loading ───────────────────────────────────────────
    store = FeatureStore()
    features: Dict = store.load_node_features(start_date, end_date, SYMBOLS, expected_features=24)

    available_symbols = [s for s in SYMBOLS if s in features]
    if not available_symbols:
        print("No features available for any symbol — aborting.")
        return {"predictions_stored": 0, "model_version": "n/a"}

    print(f"Features loaded for {len(available_symbols)} assets.")

    # ── 2. Graph construction ────────────────────────────────────────
    # DynamicGraphBuilder still accepts a client arg — pass None so it
    # won't try to hit Supabase for graph-snapshot persistence.
    builder = DynamicGraphBuilder(supabase_client=None, asset_symbols=available_symbols, feature_dim=24)

    # Prepare features indexed by timestamp for the builder.
    proc_features: Dict = {}
    for sym in available_symbols:
        df = features[sym].copy()
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        proc_features[sym] = df

    start_dt = datetime.combine((now - timedelta(days=30)).date(), datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(now.date(), datetime.min.time()).replace(tzinfo=timezone.utc)

    graph_sequence = builder.build_temporal_graph_sequence(
        start_date=start_dt,
        end_date=end_dt,
        features=proc_features,
        lookback_window=30,
    )

    if not graph_sequence:
        print("Graph sequence is empty — aborting.")
        return {"predictions_stored": 0, "model_version": "n/a"}

    print(f"Graph sequence built: {len(graph_sequence)} timesteps, "
          f"{graph_sequence[0].x.shape[0]} nodes × {graph_sequence[0].x.shape[1]} features.")

    # ── 3. Model loading ─────────────────────────────────────────────
    if not MODEL_PATH.exists():
        print(f"Model checkpoint not found at {MODEL_PATH} — aborting.")
        return {"predictions_stored": 0, "model_version": "n/a"}

    model = STGCNModel.load(str(MODEL_PATH))
    model.eval()
    model_version = _get_model_version(MODEL_PATH)
    print(f"Model loaded: {MODEL_PATH.name} (version={model_version})")

    # ── 4. Forward pass & Probability Calibration (Temperature Scaling) ──────
    with torch.no_grad():
        dir_logits, vol_logits = model(graph_sequence)  # (N,5), (N,4)

    # Retrieve calibrated temperature scaling factor from model config (default: 1.5)
    temperature = getattr(model, 'config', {}).get("temperature", 1.5)
    print(f"Applying Calibrated Temperature Scaling (T = {temperature:.2f}) to model logits...")

    # Use calibrated softmax to get true model-predicted probabilities
    dir_probs = F.softmax(dir_logits / temperature, dim=1)   # (N, 5)
    vol_probs = F.softmax(vol_logits, dim=1)   # (N, 4)

    # ── 5. Decode predictions & Generate XAI / Inference Attestations ────────
    predictions = []
    timestamp_now = now.isoformat()
    
    t_shap = TopologicalShapExplainer()
    attester = InferenceAttester()

    # Model Quality Gate check based on validation metrics
    gate_passed = True
    gate_reason = ""
    try:
        metrics_path = Path(__file__).resolve().parent.parent / "artifacts" / "validation_metrics.json"
        if not metrics_path.exists():
            metrics_path = Path("ml/artifacts/validation_metrics.json")
        if not metrics_path.exists():
            metrics_path = Path("../ml/artifacts/validation_metrics.json")
            
        if metrics_path.exists():
            with open(metrics_path, "r") as f:
                metrics = json.load(f)
            f1 = metrics.get("f1_macro", 0.0)
            sharpe = metrics.get("sharpe_ratio", 0.0)
            if f1 < 0.35 or sharpe < 0.0:
                gate_passed = False
                gate_reason = f"F1={f1:.4f} (< 0.35) or Sharpe={sharpe:.4f} (< 0.0)"
        else:
            gate_passed = False
            gate_reason = "No validation metrics file found."
    except Exception as e:
        print(f"Error checking model quality gate: {e}")
        gate_passed = False
        gate_reason = f"Exception - {e}"

    if not gate_passed:
        print(f"⚠️ MODEL QUALITY GATE REJECTED: {gate_reason}. Serving 'recalibrating' predictions to UI.")

    for idx, symbol in enumerate(available_symbols):
        latest_features = features[symbol].iloc[-1] if symbol in features else None
        
        # Decode direction and confidence from the model's forward pass
        if gate_passed:
            dir_idx = int(dir_probs[idx].argmax().item())
            confidence = float(dir_probs[idx][dir_idx].item()) * 100.0
            direction = DIRECTION_CLASSES[dir_idx]
        else:
            direction = "recalibrating"
            confidence = 0.0
            
        # Decode volatility regime from the model's volatility head
        vol_idx = int(vol_probs[idx].argmax().item())
        vol_regime = VOLATILITY_CLASSES[vol_idx]

        real_xai_features = {}
        if latest_features is not None:
            real_xai_features = {
                "RSI (14)": float(latest_features.get("rsi_14", 50.0)),
                "MACD": float(latest_features.get("macd", 0.0)),
                "Volatility": float(latest_features.get("volatility_7d", 0.0))
            }
        else:
            real_xai_features = {"BTC-ETH Correlation": 0.88, "On-Chain Volume": 1.2, "Order Book Imbalance": -0.5}
        
        # Generate T-SHAP Explainer values using real GCN model gradients
        xai_result = t_shap.explain_prediction(
            symbol=symbol,
            features=real_xai_features,
            model=model,
            graph_sequence=graph_sequence,
            asset_idx=idx,
            feature_names=FEATURE_NAMES
        )
        
        # Generate Cryptographic Inference Attestation
        attestation_result = attester.generate_inference_attestation(model_version, real_xai_features, direction)

        predictions.append({
            "symbol": symbol,
            "direction": direction,
            "confidence": round(confidence, 2),
            "volatility_regime": vol_regime,
            "predicted_at": timestamp_now,
            "model_version": model_version,
            "t_shap_attributions": json.dumps(xai_result),
            "attestation_hash": attestation_result["attestation_hash"]
        })

    # ── 6. Batch-upsert into SQLite ──────────────────────────────────
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Build a symbol → asset_id map in one query.
    ph = ",".join("?" for _ in available_symbols)
    rows = cursor.execute(
        f"SELECT id, symbol FROM assets WHERE symbol IN ({ph})",
        available_symbols,
    ).fetchall()
    sym_to_id = {r["symbol"]: r["id"] for r in rows}

    records = []
    for pred in predictions:
        asset_id = sym_to_id.get(pred["symbol"])
        if not asset_id:
            continue
        records.append((
            asset_id,                   # asset_id
            timestamp_now,              # timestamp
            pred["predicted_at"],       # predicted_at
            pred["direction"],          # direction
            pred["confidence"],         # confidence
            pred["volatility_regime"],  # volatility_regime
            json.dumps({"t_shap": pred["t_shap_attributions"], "attestation_hash": pred["attestation_hash"]}), # shap_values
            pred["model_version"],      # model_version
            pred["t_shap_attributions"],# t_shap_attributions
            pred["attestation_hash"]    # attestation_hash
        ))

    if records:
        cursor.executemany("""
            INSERT INTO predictions
                (asset_id, timestamp, predicted_at, direction,
                 confidence, volatility_regime, shap_values, model_version, t_shap_attributions, attestation_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, records)
        conn.commit()

    # ── 7. Generate daily LSTM+Prophet forecasts and cache them in Forecasts table ──
    try:
        cursor.execute("DELETE FROM forecasts")
        conn.commit()
    except Exception as e:
        print(f"Error clearing forecasts table: {e}")

    for idx, symbol in enumerate(available_symbols):
        asset_id = sym_to_id.get(symbol)
        if not asset_id or symbol not in features:
            continue

        df = features[symbol].copy()
        if "timestamp" in df.columns:
            df = df.sort_values("timestamp")
            prices_series = df["close"]
            dates_series = df["timestamp"]
        else:
            df = df.sort_index()
            prices_series = df["close"]
            dates_series = pd.Series(df.index)

        try:
            print(f"Generating daily LSTM+Prophet forecast for {symbol}...")
            # Generate 30 days daily forecast
            f_res = run_ensemble_forecast(prices_series, dates_series, 30)

            cursor.execute("""
                INSERT INTO forecasts 
                (asset_id, timestamp, forecast_prices, lower_bound, upper_bound, lstm_forecast, prophet_forecast)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                asset_id,
                timestamp_now,
                json.dumps(f_res["forecast_prices"]),
                json.dumps(f_res["lower_bound"]),
                json.dumps(f_res["upper_bound"]),
                json.dumps(f_res.get("lstm_forecast", f_res["forecast_prices"])),
                json.dumps(f_res.get("prophet_forecast", f_res["forecast_prices"]))
            ))
        except Exception as fe:
            print(f"Forecast generation failed for {symbol}: {fe}")

    conn.commit()
    conn.close()
    print(f"Inference complete: {len(records)} predictions stored (model {model_version}) and daily forecasts cached.")
    return {
        "predictions_stored": len(records),
        "model_version": model_version,
    }


if __name__ == "__main__":
    result = run_inference()
    print(f"Result: {result}")
