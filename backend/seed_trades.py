import sqlite3
import json
import hashlib
import os
from datetime import datetime, timezone, timedelta

def seed_trades():
    db_path = os.getenv("DATABASE_PATH") or os.path.join(os.path.dirname(__file__), 'cryptograph.db')
    if not os.path.exists(db_path) and os.path.exists(os.path.join('backend', 'cryptograph.db')):
        db_path = os.path.join('backend', 'cryptograph.db')

    print(f"Connecting to database at: {db_path}")
    conn = sqlite3.connect(db_path)
    
    # SQLite migrations: Rename zk_snark_proof and create forecasts table if needed
    try:
        mig_cursor = conn.cursor()
        # 1. Rename column
        table_exists = mig_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='predictions'").fetchone()
        if table_exists:
            mig_cursor.execute("PRAGMA table_info(predictions)")
            columns = mig_cursor.fetchall()
            column_names = [col[1] for col in columns]
            if "zk_snark_proof" in column_names and "attestation_hash" not in column_names:
                print("[Migration] Renaming predictions.zk_snark_proof to attestation_hash...")
                mig_cursor.execute("ALTER TABLE predictions RENAME COLUMN zk_snark_proof TO attestation_hash")
                conn.commit()
                
        # 2. Create forecasts table
        mig_cursor.execute("""
            CREATE TABLE IF NOT EXISTS forecasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id VARCHAR NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
                timestamp DATETIME NOT NULL,
                forecast_prices TEXT NOT NULL,
                lower_bound TEXT NOT NULL,
                upper_bound TEXT NOT NULL,
                lstm_forecast TEXT,
                prophet_forecast TEXT
            )
        """)
        mig_cursor.execute("CREATE INDEX IF NOT EXISTS idx_forecasts_asset_time ON forecasts(asset_id, timestamp)")
        conn.commit()
    except Exception as e:
        print(f"Error performing SQLite migrations in seeder: {e}")
        
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Clear existing states, trades, debates and proofs
    cursor.execute("DELETE FROM portfolio_state")
    cursor.execute("DELETE FROM trade_history")
    cursor.execute("DELETE FROM trade_debates")
    cursor.execute("DELETE FROM proof_of_performance")
    conn.commit()

    now = datetime.now(timezone.utc)

    # Fetch available assets
    assets = cursor.execute("SELECT id, symbol FROM assets").fetchall()
    if not assets:
        print("[Seeding Error] No assets found in the database. Please run migrations/collectors first.")
        conn.close()
        return

    asset_map = {a["symbol"]: a["id"] for a in assets}
    active_symbols = list(asset_map.keys())

    # Ensure we have ohlcv data for simulation.
    # If no ohlcv rows exist, insert some mock historical data.
    ohlcv_count = cursor.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
    if ohlcv_count == 0:
        print("No OHLCV data found. Inserting mock daily prices for backtest simulation...")
        # Insert 30 days of mock prices for BTC, ETH, SOL
        mock_bases = {"BTC": 60000.0, "ETH": 3000.0, "SOL": 130.0, "LINK": 15.0}
        for sym, base in mock_bases.items():
            if sym not in asset_map:
                continue
            asset_id = asset_map[sym]
            for i in range(40):
                day_ts = (now - timedelta(days=i)).isoformat()
                price = base * (1 + 0.01 * (i % 5 - 2)) # slight oscillation
                cursor.execute("""
                    INSERT INTO ohlcv (asset_id, timestamp, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (asset_id, day_ts, price*0.99, price*1.02, price*0.98, price, 1000.0))
        conn.commit()

    # Ensure we have predictions for backtest.
    # If predictions are empty, insert some mock predictions.
    pred_count = cursor.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    if pred_count == 0:
        print("No predictions found. Inserting mock daily predictions for backtest...")
        mock_dirs = ["strong_up", "up", "neutral", "down", "strong_down"]
        for idx, sym in enumerate(["BTC", "ETH", "SOL", "LINK"]):
            if sym not in asset_map:
                continue
            asset_id = asset_map[sym]
            for i in range(20):
                day_ts = (now - timedelta(days=i)).isoformat()
                direction = mock_dirs[(i + idx) % 5]
                confidence = 60.0 + (i * 2 + idx) % 35
                cursor.execute("""
                    INSERT INTO predictions (asset_id, timestamp, predicted_at, direction, confidence, volatility_regime, shap_values, model_version, t_shap_attributions, attestation_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (asset_id, day_ts, day_ts, direction, confidence, "medium", "{}", "v1.0.0", "{}", f"attest_mock_hash_{idx}_{i}"))
        conn.commit()

    # --- 10-Day Paper-Trading Backtest Simulation ---
    cash_balance = 100000.0
    holdings = {} # symbol -> {"qty": float, "avg_price": float, "total_invested": float}
    portfolio_history = []
    trade_history = []
    debates_history = []

    print("Running historical backtest simulation over the last 10 days...")

    # We evaluate from Day 10 (oldest) down to Day 1 (newest)
    for day in range(10, 0, -1):
        day_date = now - timedelta(days=day)
        day_iso = day_date.isoformat()

        # Gather day's prices and predictions
        day_prices = {}
        day_predictions = {}
        for sym in active_symbols:
            asset_id = asset_map[sym]
            
            # Fetch closest price on or before this day
            price_row = cursor.execute("""
                SELECT close FROM ohlcv 
                WHERE asset_id = ? AND timestamp <= ? 
                ORDER BY timestamp DESC LIMIT 1
            """, (asset_id, day_iso)).fetchone()
            if price_row:
                day_prices[sym] = price_row["close"]

            # Fetch closest prediction on or before this day
            pred_row = cursor.execute("""
                SELECT direction, confidence, attestation_hash FROM predictions 
                WHERE asset_id = ? AND timestamp <= ? 
                ORDER BY timestamp DESC LIMIT 1
            """, (asset_id, day_iso)).fetchone()
            if pred_row:
                day_predictions[sym] = {
                    "direction": pred_row["direction"],
                    "confidence": pred_row["confidence"],
                    "attestation_hash": pred_row["attestation_hash"]
                }

        # Benchmark calculation using BTC price relative change
        btc_price = day_prices.get("BTC", 60000.0)
        btc_benchmark_val = 100000.0
        if portfolio_history:
            prev_btc_price = portfolio_history[-1]["btc_price"]
            btc_return = (btc_price - prev_btc_price) / prev_btc_price
            btc_benchmark_val = portfolio_history[-1]["btc_benchmark"] * (1 + btc_return)

        # Run simulated trading decisions for the day
        for sym in ["BTC", "ETH", "SOL", "LINK"]:
            if sym not in day_prices or sym not in day_predictions:
                continue
            
            price = day_prices[sym]
            pred = day_predictions[sym]
            qty_held = holdings.get(sym, {}).get("qty", 0.0)

            # BUY signal: If prediction is strong_up/up and we have cash, buy a slice
            if pred["direction"] in ["strong_up", "up"] and qty_held == 0:
                allocation = 20000.0 # Allocate $20,000 per trade
                if cash_balance >= allocation:
                    qty = allocation / price
                    holdings[sym] = {
                        "qty": qty,
                        "avg_price": price,
                        "total_invested": allocation
                    }
                    cash_balance -= allocation

                    trade_record = {
                        "timestamp": day_iso,
                        "symbol": sym,
                        "side": "buy",
                        "qty": qty,
                        "price": price,
                        "total": allocation,
                        "reason": f"ST-GCN bullish forecast ({pred['direction']}) with {pred['confidence']}% confidence. Validated by on-chain adoption metrics.",
                        "conf": pred["confidence"],
                        "status": "EXECUTED",
                        "pnl": 0.0
                    }
                    trade_history.append(trade_record)

                    debate_record = {
                        "timestamp": day_iso,
                        "symbol": sym,
                        "dir": pred["direction"],
                        "conf": pred["confidence"],
                        "macro": "Favorable global liquidity metrics. Easing yields support risk-on asset allocations.",
                        "onchain": "Increased active address counts and transaction throughput detected on ledger.",
                        "sentiment": "Crowd psychology shifts to positive greed levels. Social mentions breakout.",
                        "decision": "EXECUTE_BUY",
                        "reasoning": f"Cohesion between macro metrics and high ST-GCN confidence ({pred['confidence']}%) suggests high asymmetry. Authorized buy trade."
                    }
                    debates_history.append(debate_record)

            # SELL signal: If prediction is down/strong_down and we hold the asset, liquidate it
            elif pred["direction"] in ["strong_down", "down"] and qty_held > 0:
                gross_value = qty_held * price
                pnl = gross_value - holdings[sym]["total_invested"]
                cash_balance += gross_value
                del holdings[sym]

                trade_record = {
                    "timestamp": day_iso,
                    "symbol": sym,
                    "side": "sell",
                    "qty": qty_held,
                    "price": price,
                    "total": gross_value,
                    "reason": f"ST-GCN bearish forecast ({pred['direction']}) signals momentum shift. Liquidating position.",
                    "conf": pred["confidence"],
                    "status": "EXECUTED",
                    "pnl": pnl
                }
                trade_history.append(trade_record)

                debate_record = {
                    "timestamp": day_iso,
                    "symbol": sym,
                    "dir": pred["direction"],
                    "conf": pred["confidence"],
                    "macro": "Tightening macro trends or localized sector consolidation ahead.",
                    "onchain": "Large exchange inflows or whale sell-offs detected.",
                    "sentiment": "Social volume shows bearish divergences or cooling hype.",
                    "decision": "EXECUTE_SELL",
                    "reasoning": "High confidence bearish trend prediction. Recommended immediate risk off/liquidation."
                }
                debates_history.append(debate_record)

        # Calculate current holdings valuation
        holdings_value = 0.0
        for sym, h in holdings.items():
            current_price = day_prices.get(sym, h["avg_price"])
            holdings_value += h["qty"] * current_price

        total_value = cash_balance + holdings_value

        portfolio_history.append({
            "timestamp": day_iso,
            "cash": cash_balance,
            "holdings": holdings_value,
            "total": total_value,
            "btc_benchmark": btc_benchmark_val,
            "btc_price": btc_price,
            "day_num": day
        })

    # Write simulated data to SQLite tables
    portfolio_map = {}
    for entry in portfolio_history:
        cursor.execute("""
            INSERT INTO portfolio_state (timestamp, cash_balance, holdings_value, total_value, btc_benchmark_value)
            VALUES (?, ?, ?, ?, ?)
        """, (entry["timestamp"], entry["cash"], entry["holdings"], entry["total"], entry["btc_benchmark"]))
        portfolio_map[entry["day_num"]] = cursor.lastrowid

    # Write trade history and map to closest portfolio state ID
    trade_id_mapping = []
    for t in trade_history:
        cursor.execute("""
            INSERT INTO trade_history (timestamp, symbol, side, quantity, price, total_usd, reason, confidence, status, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (t["timestamp"], t["symbol"], t["side"], t["qty"], t["price"], t["total"], t["reason"], t["conf"], t["status"], t["pnl"]))
        trade_id_mapping.append((cursor.lastrowid, t))

    # Write debates
    for d in debates_history:
        cursor.execute("""
            INSERT INTO trade_debates (timestamp, symbol, stgcn_direction, stgcn_confidence, macro_analysis, onchain_analysis, sentiment_analysis, cio_decision, cio_reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (d["timestamp"], d["symbol"], d["dir"], d["conf"], d["macro"], d["onchain"], d["sentiment"], d["decision"], d["reasoning"]))

    # Write Proof of Performance chained Merkle hashes
    prev_hash = "0x0000000000000000000000000000000000000000000000000000000000000000"
    for entry in portfolio_history:
        p_id = portfolio_map[entry["day_num"]]
        
        # Collect trades up to this timestamp
        day_trades = [t for t_id, t in trade_id_mapping if t["timestamp"] <= entry["timestamp"]]
        trade_data = [
            {
                "symbol": t["symbol"],
                "side": t["side"],
                "quantity": t["qty"],
                "price": t["price"],
                "pnl": t["pnl"]
            } for t in day_trades
        ]
        
        payload = {
            "portfolio_id": p_id,
            "cash_balance": entry["cash"],
            "holdings_value": entry["holdings"],
            "total_value": entry["total"],
            "btc_benchmark": entry["btc_benchmark"],
            "timestamp": entry["timestamp"],
            "recent_trades": trade_data,
            "previous_hash": prev_hash
        }
        
        payload_str = json.dumps(payload, sort_keys=True)
        state_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        prev_hash = state_hash
        
        cursor.execute("""
            INSERT INTO proof_of_performance (timestamp, portfolio_state_id, state_hash, published_to_ipfs)
            VALUES (?, ?, ?, ?)
        """, (entry["timestamp"], p_id, state_hash, None))

    conn.commit()
    conn.close()
    print("Successfully completed the 10-day backtest simulation and populated portfolio history!")

if __name__ == "__main__":
    seed_trades()
