"""
Full training pipeline: hyperopt -> train -> backtest -> explain -> register.
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import torch
import os
import numpy as np
sys = __import__("sys")
os.environ["WANDB_MODE"] = "disabled"

# Add project root to python path to resolve ModuleNotFoundError: No module named 'ml'
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from ml.data.feature_store.store import FeatureStore
from ml.graph.graph_builder import DynamicGraphBuilder
from ml.models.stgcn import STGCNModel
from ml.training.trainer import STGCNTrainer
from ml.evaluation.explainability import explain_all_assets
from ml.hyperopt.optuna_search import run_hyperopt
from ml.training.ensemble import get_ensemble_model

# Ensure artifacts directory exists
os.makedirs("ml/artifacts", exist_ok=True)

def get_db_symbols():
    try:
        from app.db.database import SessionLocal
        from app.db.models_sqla import Asset
        db = SessionLocal()
        try:
            assets = db.query(Asset.symbol).all()
            if assets:
                return [a.symbol for a in assets]
        finally:
            db.close()
    except Exception:
        pass
    return ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE"]

SYMBOLS = get_db_symbols()

def main():
    # CPU usage constraints for Intel i3 compatibility
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)

    print("[Step 1] Loading features from FeatureStore...")
    store = FeatureStore()
    now = datetime.now(timezone.utc)
    # 2 years of data
    start_date = (now - timedelta(days=730)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")
    
    features = store.load_node_features(start_date, end_date, SYMBOLS, expected_features=24)
    
    available_symbols = [s for s in SYMBOLS if s in features and not features[s].empty]
    if not available_symbols:
        print("No features found. Run ingestion first.")
        return
        
    print(f"Loaded features for {len(available_symbols)} assets.")

    print("\n[Step 2] Loading or Running Optuna hyperparameter search...")
    current = Path(__file__).resolve()
    workspace_root = current
    for parent in current.parents:
        if (parent / ".git").exists() or (parent / "README.md").exists() or (parent / "ARCHITECTURE.md").exists():
            workspace_root = parent
            break
            
    artifacts_dir = workspace_root / "ml" / "artifacts"
    params_path = artifacts_dir / "best_params.json"
    
    import time
    if params_path.exists():
        # Invalidate Optuna cache if older than 7 days
        file_age_days = (time.time() - params_path.stat().st_mtime) / (24 * 3600)
        if file_age_days > 7:
            print(f"Hyperparameter cache is {file_age_days:.1f} days old. Invalidating and re-running Optuna search...")
            best_params = run_hyperopt(features, available_symbols)
        else:
            print(f"Found existing hyperparameter configuration at {params_path}. Skipping Optuna search.")
            with open(params_path, "r") as f:
                best_params = json.load(f)
    else:
        print("No existing hyperparameter configuration found. Starting Optuna search...")
        best_params = run_hyperopt(features, available_symbols)
    
    print("\n[Step 3] Loading best hyperparameters...")
    best_params["max_epochs"] = int(os.environ.get("MAX_EPOCHS", 5))  # 5 epochs by default for fast local CPU runs
    print(f"Best Params: {best_params}")
    
    print("\n[Step 4] Training STGCNModel with best hyperparameters...")
    
    # Build full graph sequence for training
    print("Building daily graphs and dates...")
    builder = DynamicGraphBuilder(supabase_client=None, asset_symbols=available_symbols, feature_dim=24)
    
    proc_features = {}
    for sym in available_symbols:
        df = features[sym].copy()
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        
        # Floor dates to Day boundary for daily matching
        df.index = df.index.floor('D')
        df = df[~df.index.duplicated(keep='last')]
        proc_features[sym] = df

    # Find the range of days
    start_dt = (now - timedelta(days=730)).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    end_dt = now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    
    all_graphs = []
    graph_dates = []
    current_date = start_dt
    while current_date <= end_dt:
        missing_count = 0
        for sym in available_symbols:
            if sym not in proc_features or current_date not in proc_features[sym].index:
                missing_count += 1
                
        # If at least 90% of assets have data for this day, build graph
        if missing_count / len(available_symbols) <= 0.1:
            g = builder.build_graph(current_date, proc_features)
            all_graphs.append(g)
            graph_dates.append(current_date)
            
        current_date += timedelta(days=1)
        
    print(f"Built {len(all_graphs)} daily graphs.")
    lookback_window = best_params.get("lookback_window", 14)
    
    # Chronological split using TimeSeriesSplit to guarantee no data leakage
    from sklearn.model_selection import TimeSeriesSplit
    tscv = TimeSeriesSplit(n_splits=2)
    # This creates a strict train/val/test split chronologically
    splits = list(tscv.split(all_graphs))
    # We will use simple strict chronological indexing to map 70/15/15 to match the original architecture
    split_train_idx = int(len(all_graphs) * 0.70)
    split_val_idx = int(len(all_graphs) * 0.85)
    
    # Ensure we have enough data
    if len(all_graphs) < lookback_window + 5:
        print("Not enough graphs built to form sliding windows.")
        return
        
    print("Pre-computing dynamic return thresholds on train split...")
    train_returns_raw = []
    for idx in range(lookback_window, split_train_idx):
        target_date = graph_dates[idx]
        for sym in available_symbols:
            df = proc_features[sym]
            if target_date in df.index:
                ret = df.loc[target_date, "returns_1d"]
                if not pd.isna(ret):
                    train_returns_raw.append(ret)
                    
    if len(train_returns_raw) > 100:
        threshold_low = float(np.percentile(train_returns_raw, 33.3))
        threshold_high = float(np.percentile(train_returns_raw, 66.7))
    else:
        threshold_low = -0.01
        threshold_high = 0.01
        
    print(f"Computed thresholds: Low={threshold_low:.6f}, High={threshold_high:.6f}")
    
    def classify_direction(ret):
        if pd.isna(ret):
            return 1  # neutral
        if ret <= threshold_low:
            return 0  # down
        elif ret >= threshold_high:
            return 2  # up
        else:
            return 1  # neutral

    def classify_volatility(vol):
        if pd.isna(vol) or vol < 0.025:
            return 0  # low
        elif vol > 0.065:
            return 3  # extreme
        elif vol > 0.040:
            return 2  # high
        else:
            return 1  # medium

    precomputed_labels = []
    for idx in range(len(all_graphs)):
        target_date = graph_dates[idx]
        dir_labels_list = []
        vol_labels_list = []
        returns_list = []
        vol_raw_list = []
        
        for sym in available_symbols:
            df = proc_features[sym]
            if target_date in df.index:
                ret = df.loc[target_date, "returns_1d"]
                vol = df.loc[target_date, "volatility_7d"]
            else:
                ret = 0.0
                vol = 0.0
            
            dir_labels_list.append(classify_direction(ret))
            vol_labels_list.append(classify_volatility(vol))
            returns_list.append(ret if not pd.isna(ret) else 0.0)
            vol_raw_list.append(vol if not pd.isna(vol) else 0.0)
            
        dir_tensor = torch.tensor(dir_labels_list, dtype=torch.long)
        vol_tensor = torch.tensor(vol_labels_list, dtype=torch.long)
        ret_tensor = torch.tensor(returns_list, dtype=torch.float32)
        vol_raw_tensor = torch.tensor(vol_raw_list, dtype=torch.float32)
        precomputed_labels.append((dir_tensor, vol_tensor, ret_tensor, vol_raw_tensor))

    print(f"Building sliding window datasets (lookback={lookback_window})...")

    def build_sliding_windows(start_idx, end_idx):
        dataset = []
        for idx in range(start_idx, end_idx):
            input_seq = all_graphs[idx - lookback_window + 1 : idx + 1]
            dir_tensor, vol_tensor, ret_tensor, vol_raw_tensor = precomputed_labels[idx + 1]
            dataset.append((input_seq, dir_tensor, vol_tensor, ret_tensor, vol_raw_tensor))
        return dataset

    train_graphs = build_sliding_windows(lookback_window, split_train_idx - 1)
    val_graphs = build_sliding_windows(split_train_idx, split_val_idx - 1)
    test_graphs = build_sliding_windows(split_val_idx, len(all_graphs) - 2)
    
    print(f"Dataset summary: {len(train_graphs)} train, {len(val_graphs)} val, {len(test_graphs)} test samples.")
    
    # Calculate direction class counts in train dataset for inverse frequency weights
    dir_counts = [0] * 3
    for item in train_graphs:
        dir_labels = item[1]
        for val in dir_labels.tolist():
            if 0 <= val < 3:
                dir_counts[val] += 1
    if any(c == 0 for c in dir_counts):
        dir_counts = [max(1, c) for c in dir_counts]
    best_params["direction_class_counts"] = dir_counts
    print(f"Computed training set class distribution: {dir_counts}")
    
    N = len(available_symbols)
    model = STGCNModel(
        in_features=24,
        hidden_dim=best_params.get("hidden_dim", 32),
        gat_heads_1=best_params.get("gat_heads_1", 2),
        gat_heads_2=best_params.get("gat_heads_2", 1),
        transformer_layers=best_params.get("transformer_layers", 1),
        dropout=best_params.get("dropout", 0.2),
        num_direction_classes=3,
        use_tcn=best_params.get("use_tcn", True)
    )
    
    # Enable state-of-the-art SAM regularization for flat-minima convergence
    best_params["use_sam"] = True
    best_params["use_fgm"] = False
    best_params["fgm_epsilon"] = 0.05
    
    trainer = STGCNTrainer(model, train_graphs, val_graphs, best_params)
    trainer.fit()
    
    print("\n[Step 4.5] Calibrating model probabilities using Temperature Scaling...")
    best_temp = 1.0
    best_nll = float('inf')
    model.eval()
    
    all_logits = []
    all_targets = []
    with torch.no_grad():
        for item in val_graphs:
            graph_seq, dir_labels = item[0], item[1]
            graph_seq = [g.to(trainer.device) for g in graph_seq]
            dir_logits, _ = model(graph_seq)
            all_logits.append(dir_logits.cpu())
            all_targets.append(dir_labels.cpu())
            
    if all_logits:
        val_logits = torch.cat(all_logits, dim=0)
        val_targets = torch.cat(all_targets, dim=0)
        
        for t_candidate in np.arange(0.1, 3.0, 0.05):
            scaled_logits = val_logits / t_candidate
            nll = torch.nn.functional.cross_entropy(scaled_logits, val_targets).item()
            if nll < best_nll:
                best_nll = nll
                best_temp = float(t_candidate)
                
    # Save the calibrated parameters into config using an absolute workspace path to prevent package side-effects
    current = Path(__file__).resolve()
    workspace_root = current
    for parent in current.parents:
        if (parent / ".git").exists() or (parent / "README.md").exists() or (parent / "ARCHITECTURE.md").exists():
            workspace_root = parent
            break
            
    artifacts_dir = workspace_root / "ml" / "artifacts"
    best_model_path = artifacts_dir / "best_model.pt"
    
    model.config["temperature"] = best_temp
    model.config["threshold_low"] = threshold_low
    model.config["threshold_high"] = threshold_high
    model.save(str(best_model_path))

    print("\n[Step 4.6] Running out-of-sample final evaluation on held-out Test Set using Snapshot Ensemble...")
    # Load the ensemble of top models
    ensemble_model = get_ensemble_model(str(artifacts_dir), limit=3, device=trainer.device)
    
    all_targets_test = []
    all_preds_test = []
    all_probs_test = []
    all_returns_test = []
    
    with torch.no_grad():
        for item in test_graphs:
            graph_seq, dir_labels, returns = item[0], item[1], item[3]
            graph_seq = [g.to(trainer.device) for g in graph_seq]
            probs, _ = ensemble_model(graph_seq)
            preds = torch.argmax(probs, dim=-1)
            
            all_targets_test.append(dir_labels.cpu())
            all_preds_test.append(preds.cpu())
            all_probs_test.append(probs.cpu())
            all_returns_test.append(returns.cpu() if isinstance(returns, torch.Tensor) else torch.tensor(returns))
            
    if all_targets_test:
        y_true = torch.cat(all_targets_test, dim=0).numpy()
        y_pred = torch.cat(all_preds_test, dim=0).numpy()
        y_prob = torch.cat(all_probs_test, dim=0).numpy()
        ret_arr = torch.cat(all_returns_test, dim=0).numpy()
        
        # Calculate daily portfolio returns
        signal_weights = np.zeros_like(y_pred, dtype=np.float32)
        signal_weights[y_pred == 2] = 1.0   # BUY
        signal_weights[y_pred == 1] = 0.0   # HOLD
        signal_weights[y_pred == 0] = -1.0  # SELL
        
        num_assets = len(available_symbols)
        ret_flat = ret_arr.flatten()
        trade_returns = signal_weights * ret_flat
        trade_returns = trade_returns.reshape(-1, num_assets)
        daily_portfolio_returns = trade_returns.mean(axis=1)
        
        from ml.training.metrics import compute_all_metrics
        clf_metrics = compute_all_metrics(y_true, y_pred, y_prob, daily_portfolio_returns)
        
        metrics_log = {
            "sharpe_ratio": float(clf_metrics.get("sharpe_ratio", 0.0)),
            "sortino_ratio": float(clf_metrics.get("sortino_ratio", 0.0)),
            "max_drawdown": float(clf_metrics.get("max_drawdown", 0.0)),
            "profit_factor": float(clf_metrics.get("profit_factor", 1.0)),
            "win_rate": float(clf_metrics.get("win_rate", 0.0)),
            "f1_macro": float(clf_metrics.get("f1_macro", 0.0)),
            "precision_macro": float(clf_metrics.get("precision_macro", 0.0)),
            "recall_macro": float(clf_metrics.get("recall_macro", 0.0))
        }
        
        metrics_save_path = artifacts_dir / "validation_metrics.json"
        with open(metrics_save_path, "w") as f:
            json.dump(metrics_log, f, indent=4)
        print(f"Audited Out-of-Sample Test Set Metrics: F1={metrics_log['f1_macro']:.4f}, Sharpe={metrics_log['sharpe_ratio']:.4f}")
    
    print("\n[Step 5] Computing Captum explainability...")
    feature_names = [
        "open", "high", "low", "close", "volume", 
        "rsi_14", "macd", "macd_signal", "atr_14", "bb_width",
        "returns_1d", "returns_7d", "volatility_7d", 
        "sentiment_score", "fear_greed_norm", "community_score", "public_interest", 
        "sentiment_rolling_3d", "sentiment_momentum", "market_cap_usd",
        "fed_rate", "cpi", "inflation", "vix"
    ]
    graph_sequences_dict = {sym: test_graphs[-1][0] for sym in available_symbols}
    explain_all_assets(model, graph_sequences_dict, feature_names, db_session=None)
    
    print("\n[Step 6] Registering model in SQLite...")
    # Registering model checkpoint
    model.save("ml/artifacts/best_model.pt")
    
    print("\nTraining pipeline complete")

if __name__ == "__main__":
    main()
