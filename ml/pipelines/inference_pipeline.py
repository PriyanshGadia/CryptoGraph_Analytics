"""
Daily inference pipeline.

Loads the last 30 days of features from the local SQLite FeatureStore,
builds the graph sequence via DynamicGraphBuilder, runs a real forward
pass through the trained STGCNModel, and batch-upserts predictions into
the SQLite database.
"""
import sys
from pathlib import Path
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))
if str(root_dir / "backend") not in sys.path:
    sys.path.append(str(root_dir / "backend"))

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import torch
import torch.nn.functional as F
import math

from ml.data.feature_store.store import FeatureStore
from ml.graph.graph_builder import DynamicGraphBuilder
from ml.models.stgcn import STGCNModel
from ml.pipelines.training_pipeline_enterprise import EnterpriseSTGCNModel
import json
import numpy as np

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


# Phase 9: XAI & Inference Attestation Integration
from app.ml.gnn_attribution_explainer import GNNGradientAttributionExplainer
from app.ml.inference_attester import InferenceAttester
import hashlib
from ml.models.forecast_model import run_ensemble_forecast
import pandas as pd

# ── Constants ────────────────────────────────────────────────────────
def _find_artifacts_path() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / ".git").exists() or (parent / "README.md").exists() or (parent / "ARCHITECTURE.md").exists():
            return parent / "ml" / "artifacts" / "best_model.pt"
    # Fallback
    return Path(__file__).resolve().parent.parent / "artifacts" / "best_model.pt"

MODEL_PATH = _find_artifacts_path()

DIRECTION_CLASSES = ["down", "neutral", "up"]
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
        ckpt = torch.load(model_path, map_location="cpu", weights_only=False)
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
        lookback_window=14,  # Matching new lookback_window
    )

    if not graph_sequence:
        print("Graph sequence is empty — aborting.")
        return {"predictions_stored": 0, "model_version": "n/a"}

    print(f"Graph sequence built: {len(graph_sequence)} timesteps, "
          f"{graph_sequence[0].x.shape[0]} nodes × {graph_sequence[0].x.shape[1]} features.")

    # ── 3. Model loading & Forward Pass (Memory Optimized) ───────────
    import gc
    gate_passed = True
    gate_reason = ""
    
    print(f"Attempting to load PyTorch model into memory (4GB RAM safe-mode)...")
    is_enterprise = False
    pred_np = None
    log_var_np = None
    dir_probs = None
    vol_probs = None
    model_version = "n/a"
    
    try:
        if not MODEL_PATH.exists():
            print(f"Model checkpoint not found at {MODEL_PATH} — aborting.")
            return {"predictions_stored": 0, "model_version": "n/a"}

        try:
            model = EnterpriseSTGCNModel.load(str(MODEL_PATH))
            is_enterprise = True
            print("Loaded EnterpriseSTGCNModel successfully.")
        except Exception as e_ent:
            print(f"Failed to load as EnterpriseSTGCNModel ({e_ent}), trying STGCNModel...")
            model = STGCNModel.load(str(MODEL_PATH))
        
        # Explicitly map to CPU to avoid CUDA OOM if running on low-end hardware
        model.to(torch.device("cpu"))
        model.eval()
        model_version = _get_model_version(MODEL_PATH)
        print(f"Model loaded: {MODEL_PATH.name} (version={model_version})")

        with torch.no_grad():
            if is_enterprise:
                # Enterprise STGCNModel expects batch_sequences List[List[Data]]
                pred, log_var = model([graph_sequence], return_uncertainty=True)
                pred_np = pred[0].cpu().numpy()
                log_var_np = log_var[0].cpu().numpy()
            else:
                dir_logits, vol_logits = model(graph_sequence)  # (N,3), (N,4)
                
                # Retrieve calibrated temperature scaling factor from model config (default: 1.0)
                temperature = getattr(model, 'config', {}).get("temperature", 1.0)
                print(f"Applying Calibrated Temperature Scaling (T = {temperature:.2f}) to model logits...")
                
                # Use calibrated softmax to get true model-predicted probabilities
                dir_probs = F.softmax(dir_logits / temperature, dim=1)   # (N, 3)
                vol_probs = F.softmax(vol_logits, dim=1)   # (N, 4)

        pass

        # Model Quality Gate check based on validation metrics
        try:
            if is_enterprise:
                metrics_path = Path(__file__).resolve().parent.parent / "artifacts" / "enterprise_test_metrics.json"
                if not metrics_path.exists():
                    metrics_path = Path("ml/artifacts/enterprise_test_metrics.json")
                if not metrics_path.exists():
                    metrics_path = Path("../ml/artifacts/enterprise_test_metrics.json")
                    
                if metrics_path.exists():
                    with open(metrics_path, "r") as f:
                        val_metrics = json.load(f)
                    val_rmse = val_metrics.get("ensemble_test_rmse", val_metrics.get("test_rmse", 999.0))
                    val_sharpe = val_metrics.get("strategy_sharpe_ratio", 0.0)
                    
                    if val_rmse > 25.0 or val_sharpe < -0.5:
                        gate_passed = False
                        gate_reason = f"RMSE={val_rmse:.2f}, Sharpe={val_sharpe:.2f} below threshold"
                        print(f"[QualityGate] WARN: Enterprise model failed quality gate ({gate_reason}). Serving recalibrating state.")
            else:
                metrics_path = Path(__file__).resolve().parent.parent / "artifacts" / "validation_metrics.json"
                if not metrics_path.exists():
                    metrics_path = Path("ml/artifacts/validation_metrics.json")
                if not metrics_path.exists():
                    metrics_path = Path("../ml/artifacts/validation_metrics.json")
                    
                if metrics_path.exists():
                    with open(metrics_path, "r") as f:
                        val_metrics = json.load(f)
                    val_f1 = val_metrics.get("f1_macro", 0.0)
                    val_sharpe = val_metrics.get("sharpe_ratio", 0.0)
                    
                    if val_f1 < 0.35 or val_sharpe < 0.0:
                        gate_passed = False
                        gate_reason = f"F1={val_f1:.2f}, Sharpe={val_sharpe:.2f} below threshold"
                        print(f"[QualityGate] WARN: Model failed quality gate ({gate_reason}). Serving recalibrating state.")
        except Exception as e:
            print(f"[QualityGate] Error reading validation metrics: {e}")

    except MemoryError:
        print("[MemoryError] PyTorch ST-GCN model exceeded available RAM (i3/4GB constraint). Engaging heuristic fallback.")
        gc.collect()
        gate_passed = False
    except Exception as e:
        print(f"[InferenceError] PyTorch execution failed: {e}. Engaging heuristic fallback.")
        gate_passed = False

    xai_explainer = GNNGradientAttributionExplainer()
    attester = InferenceAttester()

    # ── 5. Decode predictions & Generate XAI / Inference Attestations ────────
    scale_map = {}
    mean_map = {}
    
    scale_path = MODEL_PATH.parent / "target_scale_map.json"
    mean_path = MODEL_PATH.parent / "target_mean_map.json"
    
    if scale_path.exists():
        try:
            with open(scale_path, "r") as f:
                scale_map = json.load(f)
            print(f"Loaded target scale map from {scale_path}")
        except Exception as e:
            print(f"Error loading target scale map: {e}")
            
    if mean_path.exists():
        try:
            with open(mean_path, "r") as f:
                mean_map = json.load(f)
            print(f"Loaded target mean map from {mean_path}")
        except Exception as e:
            print(f"Error loading target mean map: {e}")

    predictions = []
    timestamp_now = now.isoformat()

    import numpy as np
    pred_mean = float(np.mean(pred_np)) if pred_np is not None else 0.0
    log_var_mean = float(np.mean(log_var_np)) if log_var_np is not None else 0.0

    for idx, symbol in enumerate(available_symbols):
        print(f"[{idx+1}/{len(available_symbols)}] Generating predictions & XAI attributions for {symbol}...")
        latest_features = features[symbol].iloc[-1] if symbol in features else None
        
        # Decode direction and confidence from the model's calibrated forward pass
        if gate_passed and is_enterprise and pred_np is not None and log_var_np is not None:
            import math
            scale = scale_map.get(symbol, 1.0)
            mean = mean_map.get(symbol, 0.0)
            
            pred_raw = pred_np[idx]
            log_var_raw = log_var_np[idx]
            
            # Calibrate by subtracting the cross-sectional mean offset
            pred_calibrated = pred_raw - pred_mean
            pred_return = pred_calibrated * scale + mean
            
            # Calibrate log-variance by centering it around 0.0 (standardized var = 1.0)
            log_var_calibrated = log_var_raw - log_var_mean
            log_var_calibrated = max(-3.0, min(2.0, log_var_calibrated))
            
            if pred_return > 0.001:
                direction = "up"
            elif pred_return < -0.001:
                direction = "down"
            else:
                direction = "neutral"
                
            std = math.exp(0.5 * log_var_calibrated) * scale
            z = abs(pred_return) / (std + 1e-8)
            prob = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
            
            confidence = round(min(98.5, 33.33 + (prob - 0.5) * 130.34), 2)
            if not (0 <= confidence <= 100):
                raise ValueError(f"Confidence score {confidence} is out of bounds [0, 100]")
                
            if direction == "up" and confidence >= 68.0:
                direction = "strong_up"
            elif direction == "down" and confidence >= 68.0:
                direction = "strong_down"
                
            vol_regime = "medium"
            if std > 0.03:
                vol_regime = "high"
            elif std < 0.01:
                vol_regime = "low"
                
        elif gate_passed and dir_probs is not None and vol_probs is not None:
            dir_idx = int(dir_probs[idx].argmax().item())
            prob = float(dir_probs[idx][dir_idx].item())  # Calibrated softmax probability in range [0.3333, 1.0]

            # Linear rescale of calibrated probability (33.33% baseline -> 33.33, 100% -> 98.50), no uncalibrated heuristic bonus
            confidence = round(min(98.5, 33.33 + (prob - 0.3333) / 0.6667 * 65.17), 2)
            if not (0 <= confidence <= 100):
                raise ValueError(f"Confidence score {confidence} is out of bounds [0, 100]")
            direction = DIRECTION_CLASSES[dir_idx]
            
            # Map 3-class outputs to high-conviction signals based on calibrated probability threshold
            if direction == "up" and confidence >= 68.0:
                direction = "strong_up"
            elif direction == "down" and confidence >= 68.0:
                direction = "strong_down"
                
            # Decode volatility regime from the model's volatility head
            vol_idx = int(vol_probs[idx].argmax().item())
            vol_regime = VOLATILITY_CLASSES[vol_idx]
        else:
            # Safe heuristic fallback when memory or quality gate fails
            direction = "neutral"
            if latest_features is not None:
                # Basic trend following fallback
                rsi = float(latest_features.get("rsi_14", 50.0))
                macd = float(latest_features.get("macd", 0.0))
                if rsi < 40 and macd > 0: direction = "up"
                elif rsi > 60 and macd < 0: direction = "down"
            
            confidence = 45.0
            vol_regime = "medium"

        # Extract features for XAI Integrated Gradients attribution
        if latest_features is not None:
            real_xai_features = {
                "RSI (14)": float(latest_features.get("rsi_14", 50.0)),
                "MACD": float(latest_features.get("macd", 0.0)),
                "Volatility": float(latest_features.get("volatility_7d", 0.0))
            }
        else:
            real_xai_features = {"BTC-ETH Correlation": 0.88, "On-Chain Volume": 1.2, "Order Book Imbalance": -0.5}
        
        # Generate GNN Gradient Attribution values using PyTorch model gradients
        if gate_passed and 'model' in locals():
            try:
                xai_result = xai_explainer.explain_prediction(
                    symbol=symbol,
                    features=real_xai_features,
                    model=model,
                    graph_sequence=graph_sequence,
                    asset_idx=idx,
                    feature_names=FEATURE_NAMES
                )
            except Exception as e_xai:
                print(f"[XAI Error] Failed to generate attribution for {symbol}: {e_xai}")
                xai_result = {
                    "rsi_14": 0.0,
                    "macd": 0.0,
                    "volatility_7d": 0.0,
                    "attributions_pct": {
                        "rsi_14": 33.33,
                        "macd": 33.33,
                        "volatility_7d": 33.33
                    }
                }
        else:
            xai_result = {
                "rsi_14": 0.0,
                "macd": 0.0,
                "volatility_7d": 0.0,
                "attributions_pct": {
                    "rsi_14": 33.33,
                    "macd": 33.33,
                    "volatility_7d": 33.33
                }
            }
        
        try:
            with open(MODEL_PATH, "rb") as f:
                checkpoint_sha256 = hashlib.sha256(f.read()).hexdigest()
        except Exception:
            checkpoint_sha256 = "unknown"
            
        try:
            edge_str = json.dumps(graph_sequence[-1].edge_index.tolist(), sort_keys=True)
            graph_digest = hashlib.sha256(edge_str.encode()).hexdigest()
        except Exception:
            graph_digest = "unknown"
        
        # Generate Cryptographic Inference Attestation
        attestation_result = attester.generate_inference_attestation(
            model_version=model_version, 
            features=real_xai_features, 
            direction=direction,
            checkpoint_sha256=checkpoint_sha256,
            graph_digest=graph_digest
        )

        confidence_val = round(confidence / 100.0, 4)
        predictions.append({
            "symbol": symbol,
            "direction": direction,
            "confidence": confidence_val, # SCALE DOWN TO 0.0-1.0 FOR SQLALCHEMY VALIDATOR
            "confidence_interval_lower": max(0.0, round(confidence_val - 0.05, 4)),
            "confidence_interval_upper": min(1.0, round(confidence_val + 0.05, 4)),
            "volatility_regime": vol_regime,
            "predicted_at": now,
            "model_version": model_version,
            "baseline_probability": 0.3333,
            "t_shap_attributions": json.dumps(xai_result, cls=NumpyEncoder),
            "attestation_hash": attestation_result["attestation_hash"]
        })

    # Free PyTorch model memory after the loop
    if 'model' in locals():
        del model
    if not is_enterprise:
        if 'dir_logits' in locals(): del dir_logits
        if 'vol_logits' in locals(): del vol_logits
    import gc
    gc.collect()

    # ── 6. Batch-upsert into SQLite via SQLAlchemy ──────────────────────────────────
    from app.db.database import SessionLocal, execute_with_retry, engine
    from app.db.models import Asset as SQLAAsset, Prediction as SQLAPrediction

    def _write_predictions():
        db = SessionLocal()
        try:
            # Get asset IDs
            assets = db.query(SQLAAsset).filter(SQLAAsset.symbol.in_(available_symbols)).all()
            sym_to_id = {a.symbol: a.id for a in assets}

            records = []
            for pred in predictions:
                asset_id = sym_to_id.get(pred["symbol"])
                if not asset_id:
                    continue
                
                # Check if it already exists to avoid unique constraint failure
                existing = db.query(SQLAPrediction).filter_by(asset_id=asset_id, timestamp=now).first()
                if existing:
                    # Update
                    existing.predicted_at = pred["predicted_at"]
                    existing.direction = pred["direction"]
                    existing.confidence = pred["confidence"]
                    existing.confidence_interval_lower = pred["confidence_interval_lower"]
                    existing.confidence_interval_upper = pred["confidence_interval_upper"]
                    existing.volatility_regime = pred["volatility_regime"]
                    existing.shap_values = {"t_shap": pred["t_shap_attributions"], "attestation_hash": pred["attestation_hash"]}
                    existing.model_version = pred["model_version"]
                    existing.baseline_probability = pred["baseline_probability"]
                    existing.t_shap_attributions = json.loads(pred["t_shap_attributions"]) if isinstance(pred["t_shap_attributions"], str) else pred["t_shap_attributions"]
                    existing.attestation_hash = pred["attestation_hash"]
                else:
                    new_pred = SQLAPrediction(
                        asset_id=asset_id,
                        timestamp=now,
                        predicted_at=pred["predicted_at"],
                        direction=pred["direction"],
                        confidence=pred["confidence"],
                        confidence_interval_lower=pred["confidence_interval_lower"],
                        confidence_interval_upper=pred["confidence_interval_upper"],
                        volatility_regime=pred["volatility_regime"],
                        shap_values={"t_shap": pred["t_shap_attributions"], "attestation_hash": pred["attestation_hash"]},
                        model_version=pred["model_version"],
                        baseline_probability=pred["baseline_probability"],
                        t_shap_attributions=json.loads(pred["t_shap_attributions"]) if isinstance(pred["t_shap_attributions"], str) else pred["t_shap_attributions"],
                        attestation_hash=pred["attestation_hash"]
                    )
                    db.add(new_pred)
                    records.append(new_pred)

            if records or assets:
                db.commit()
            
            return sym_to_id, len(predictions)
        except Exception as e:
            db.rollback()
            print(f"Error writing predictions to db: {e}")
            raise
        finally:
            db.close()

    sym_to_id, rec_count = execute_with_retry(_write_predictions)

    # ── 7. Generate daily LSTM+Prophet forecasts and cache them in Forecasts table ──
    forecast_records = []
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
            # Generate 30 days daily forecast
            f_res = run_ensemble_forecast(prices_series, dates_series, 30)
            forecast_records.append((
                asset_id,
                timestamp_now,
                json.dumps(f_res["forecast_prices"], cls=NumpyEncoder),
                json.dumps(f_res["lower_bound"], cls=NumpyEncoder),
                json.dumps(f_res["upper_bound"], cls=NumpyEncoder),
                json.dumps(f_res.get("lstm_forecast", f_res["forecast_prices"]), cls=NumpyEncoder),
                json.dumps(f_res.get("prophet_forecast", f_res["forecast_prices"]), cls=NumpyEncoder)
            ))
        except Exception as fe:
            print(f"Forecast generation failed for {symbol}: {fe}")

    if forecast_records:
        def _write_forecasts():
            fc_conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
            try:
                fc_cursor = fc_conn.cursor()
                fc_cursor.execute("PRAGMA journal_mode=WAL")
                fc_cursor.execute("PRAGMA busy_timeout=30000")
                fc_cursor.execute("DELETE FROM forecasts")
                fc_cursor.executemany("""
                    INSERT INTO forecasts 
                    (asset_id, timestamp, forecast_prices, lower_bound, upper_bound, lstm_forecast, prophet_forecast)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, forecast_records)
                fc_conn.commit()
            finally:
                fc_conn.close()

        try:
            execute_with_retry(_write_forecasts)
        except Exception as e:
            print(f"Error updating forecasts table: {e}")

    engine.dispose()
    print(f"Inference complete: {rec_count} predictions stored (model {model_version}) and daily forecasts cached.")
    return {
        "predictions_stored": rec_count,
        "model_version": model_version,
    }


main = run_inference

if __name__ == "__main__":
    result = run_inference()
    print(f"Result: {result}")
