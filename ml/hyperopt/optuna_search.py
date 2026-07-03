"""Optuna hyperparameter optimization for ST-GCN."""

import json
import os
os.environ["WANDB_MODE"] = "disabled"
from datetime import datetime
import optuna
from optuna.pruners import MedianPruner
import torch
import numpy as np
import pandas as pd
sys = __import__("sys")
from pathlib import Path

# Add project root to python path to resolve ModuleNotFoundError: No module named 'ml'
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from ml.data.feature_store.store import FeatureStore
from ml.graph.graph_builder import DynamicGraphBuilder
from ml.models.stgcn import STGCNModel
from ml.training.trainer import STGCNTrainer

def objective(trial: optuna.Trial, all_graphs: list, graph_dates: list, proc_features: dict, available_symbols: list) -> float:
    """
    Search space optimized for lower-end machines (Intel i3):
      hidden_dim:         [16, 32, 64]
      gat_heads_1:        [1, 2]
      transformer_layers: [1, 2]
      dropout:            [0.1, 0.4]
      learning_rate:      [5e-5, 5e-3]
      lookback_window:    [7, 14, 21]
      focal_gamma:        [1.0, 3.0]
    """
    hidden_dim = trial.suggest_categorical("hidden_dim", [16, 32, 64])
    gat_heads_1 = trial.suggest_categorical("gat_heads_1", [1, 2])
    transformer_layers = trial.suggest_categorical("transformer_layers", [1, 2])
    dropout = trial.suggest_float("dropout", 0.1, 0.4)
    learning_rate = trial.suggest_float("learning_rate", 5e-5, 5e-3, log=True)
    lookback_window = trial.suggest_categorical("lookback_window", [7, 14, 21])
    focal_gamma = trial.suggest_float("focal_gamma", 1.0, 3.0)

    N = len(available_symbols)
    split_train_idx = int(len(all_graphs) * 0.70)
    split_val_idx = int(len(all_graphs) * 0.85)

    # 1. Compute Percentile-based 3-Class thresholds on the training set only
    all_train_returns = []
    for idx in range(split_train_idx):
        target_date = graph_dates[idx]
        for sym in available_symbols:
            df = proc_features[sym]
            if target_date in df.index:
                ret = df.loc[target_date, "returns_1d"]
                if not pd.isna(ret):
                    all_train_returns.append(ret)
                    
    if len(all_train_returns) > 100:
        threshold_low = float(np.percentile(all_train_returns, 33.3))
        threshold_high = float(np.percentile(all_train_returns, 66.7))
    else:
        threshold_low = -0.01
        threshold_high = 0.01

    config = {
        "hidden_dim": hidden_dim,
        "gat_heads_1": gat_heads_1,
        "transformer_layers": transformer_layers,
        "dropout": dropout,
        "lr": learning_rate,
        "lookback_window": lookback_window,
        "focal_gamma": focal_gamma,
        "max_epochs": 10,  # Bounded epochs for trial run execution
        "early_stopping_patience": 3,
        "use_tcn": True,
        "use_sam": False,  # Turn off SAM during search trials to speed up 2x
        "use_fgm": False   # Turn off FGM to optimize RAM/CPU usage
    }
    
    model = STGCNModel(
        in_features=24,
        hidden_dim=hidden_dim,
        gat_heads_1=gat_heads_1,
        gat_heads_2=1,  # Keep heads at second layer small
        transformer_layers=transformer_layers,
        dropout=dropout,
        num_direction_classes=3,
        use_tcn=True
    )
    
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
            
        precomputed_labels.append((
            torch.tensor(dir_labels_list, dtype=torch.long),
            torch.tensor(vol_labels_list, dtype=torch.long),
            torch.tensor(returns_list, dtype=torch.float32),
            torch.tensor(vol_raw_list, dtype=torch.float32)
        ))

    def build_sliding_windows(start_idx, end_idx):
        dataset = []
        for idx in range(start_idx, end_idx):
            input_seq = all_graphs[idx - lookback_window + 1 : idx + 1]
            dir_tensor, vol_tensor, ret_tensor, vol_raw_tensor = precomputed_labels[idx + 1]
            dataset.append((input_seq, dir_tensor, vol_tensor, ret_tensor, vol_raw_tensor))
        return dataset

    train_graphs = build_sliding_windows(max(lookback_window, split_train_idx - 120), split_train_idx - 1)
    val_graphs = build_sliding_windows(split_train_idx, split_val_idx - 1)
    
    if not train_graphs or not val_graphs:
        print("Warning: not enough slices for Optuna search. Using subset bounds fallback.")
        return 0.0

    # Calculate direction class counts in train dataset for focal loss weights
    dir_counts = [0] * 3
    for item in train_graphs:
        dir_labels = item[1]
        for val in dir_labels.tolist():
            if 0 <= val < 3:
                dir_counts[val] += 1
    if any(c == 0 for c in dir_counts):
        dir_counts = [max(1, c) for c in dir_counts]
    config["direction_class_counts"] = dir_counts

    trainer = STGCNTrainer(model, train_graphs, val_graphs, config)
    
    best_monitored_score = 0.0
    for epoch in range(config["max_epochs"]):
        train_metrics = trainer.train_epoch()
        val_metrics = trainer.validate()
        f1 = val_metrics.get("f1_macro", 0.0)
        sharpe = val_metrics.get("sharpe_ratio", 0.0)
        
        # Composite metric
        normalized_sharpe = max(0.0, min(1.0, sharpe / 3.0)) if sharpe > 0 else 0.0
        monitored_score = 0.6 * f1 + 0.4 * normalized_sharpe
        
        print(f"  [Trial {trial.number:2d}] Epoch {epoch:2d}/{config['max_epochs']} | Loss: {train_metrics['train_loss']:.4f} | Val F1: {f1:.4f} | Sharpe: {sharpe:.4f} | Score: {monitored_score:.4f}", flush=True)
        
        if monitored_score > best_monitored_score:
            best_monitored_score = monitored_score
            
        trial.report(monitored_score, epoch)
        if trial.should_prune():
            raise optuna.TrialPruned()
            
    return best_monitored_score

def run_hyperopt(features: dict = None, available_symbols: list = None) -> dict:
    """Run Optuna study."""
    if features is None or available_symbols is None:
        return {
            "hidden_dim": 32,
            "gat_heads_1": 1,
            "transformer_layers": 1,
            "dropout": 0.2,
            "learning_rate": 0.001,
            "lookback_window": 14,
            "focal_gamma": 2.0
        }

    # Pre-build daily graphs once to optimize speed
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
        df.index = df.index.floor('D')
        df = df[~df.index.duplicated(keep='last')]
        proc_features[sym] = df

    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
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
        if missing_count / len(available_symbols) <= 0.1:
            g = builder.build_graph(current_date, proc_features)
            all_graphs.append(g)
            graph_dates.append(current_date)
        current_date += timedelta(days=1)

    if len(all_graphs) < 35:
        print("Not enough daily graphs for Optuna optimization.")
        return {
            "hidden_dim": 32,
            "gat_heads_1": 1,
            "transformer_layers": 1,
            "dropout": 0.2,
            "learning_rate": 0.001,
            "lookback_window": 14,
            "focal_gamma": 2.0
        }

    # Resolve workspace root and artifacts directory to prevent package side-effects
    current = Path(__file__).resolve()
    workspace_root = current
    for parent in current.parents:
        if (parent / ".git").exists() or (parent / "README.md").exists() or (parent / "ARCHITECTURE.md").exists():
            workspace_root = parent
            break
            
    artifacts_dir = workspace_root / "ml" / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    db_path = artifacts_dir / "optuna_study.db"
    storage_url = f"sqlite:///{db_path.as_posix()}"

    study = optuna.create_study(
        study_name="stgcn_hyperopt",
        storage=storage_url,
        load_if_exists=True,
        direction="maximize",
        pruner=MedianPruner(n_startup_trials=5)
    )
    
    completed_trials = len([t for t in study.trials if t.state.is_finished()])
    n_trials = int(os.environ.get("OPTUNA_TRIALS", 15))
    trials_to_run = max(0, n_trials - completed_trials)
    
    if trials_to_run > 0:
        print(f"Resuming Optuna study: {completed_trials} trials completed. Running {trials_to_run} more trials...")
        study.optimize(lambda t: objective(t, all_graphs, graph_dates, proc_features, available_symbols), n_trials=trials_to_run)
    else:
        print(f"Optuna study already has {completed_trials} completed trials (requested: {n_trials}). Skipping optimization.")

    best_params = study.best_params
    with open(artifacts_dir / "best_params.json", "w") as f:
        json.dump(best_params, f, indent=4)

    return best_params

if __name__ == "__main__":
    os.environ["OPTUNA_TRIALS"] = "2" 
    best = run_hyperopt(None, None)
    print(f"Hyperopt finished successfully.")
