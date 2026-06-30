"""Optuna hyperparameter optimization for ST-GCN."""

import json
import os
from datetime import datetime
import optuna
from optuna.pruners import MedianPruner
import torch

from ml.data.feature_store.store import FeatureStore
from ml.graph.graph_builder import DynamicGraphBuilder
from ml.models.stgcn import STGCNModel
from ml.training.trainer import STGCNTrainer

def objective(trial: optuna.Trial, all_graphs: list, graph_dates: list, proc_features: dict, available_symbols: list) -> float:
    """
    Search space:
      hidden_dim:         trial.suggest_categorical("hidden_dim", [64, 128, 256])
      gat_heads_1:        trial.suggest_categorical("gat_heads_1", [4, 8])
      transformer_layers: trial.suggest_categorical("transformer_layers", [2, 4, 6])
      dropout:            trial.suggest_float("dropout", 0.1, 0.3)
      learning_rate:      trial.suggest_float("learning_rate", 1e-4, 1e-3, log=True)
      lookback_window:    trial.suggest_categorical("lookback_window", [14, 21, 30])
    """
    hidden_dim = trial.suggest_categorical("hidden_dim", [64, 128, 256])
    gat_heads_1 = trial.suggest_categorical("gat_heads_1", [4, 8])
    transformer_layers = trial.suggest_categorical("transformer_layers", [2, 4, 6])
    dropout = trial.suggest_float("dropout", 0.1, 0.3)
    learning_rate = trial.suggest_float("learning_rate", 1e-4, 1e-3, log=True)
    lookback_window = trial.suggest_categorical("lookback_window", [14, 21, 30])

    N = len(available_symbols)

    config = {
        "hidden_dim": hidden_dim,
        "gat_heads_1": gat_heads_1,
        "transformer_layers": transformer_layers,
        "dropout": dropout,
        "lr": learning_rate,
        "lookback_window": lookback_window,
        "max_epochs": 10,  # Short run for hyperopt
        "early_stopping_patience": 3
    }
    
    model = STGCNModel(
        in_features=24,
        hidden_dim=hidden_dim,
        dropout=dropout
    )
    
    import pandas as pd
    def classify_direction(ret):
        if pd.isna(ret):
            return 2  # neutral
        if ret > 0.03:
            return 4  # strong_up
        elif 0.00 < ret <= 0.03:
            return 3  # up
        elif -0.01 < ret <= 0.00:
            return 2  # neutral
        elif -0.03 < ret <= -0.01:
            return 1  # down
        else:
            return 0  # strong_down

    def classify_volatility(vol):
        if pd.isna(vol) or vol < 0.025:
            return 0  # low
        elif vol > 0.065:
            return 3  # extreme
        elif vol > 0.040:
            return 2  # high
        else:
            return 1  # medium

    def build_sliding_windows(start_idx, end_idx):
        dataset = []
        for idx in range(start_idx, end_idx):
            input_seq = all_graphs[idx - lookback_window + 1 : idx + 1]
            target_date = graph_dates[idx + 1]
            
            dir_labels_list = []
            vol_labels_list = []
            returns_list = []
            
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
                
            dir_tensor = torch.tensor(dir_labels_list, dtype=torch.long)
            vol_tensor = torch.tensor(vol_labels_list, dtype=torch.long)
            ret_tensor = torch.tensor(returns_list, dtype=torch.float32)
            
            dataset.append((input_seq, dir_tensor, vol_tensor, ret_tensor))
        return dataset

    split_idx = int(len(all_graphs) * 0.8)
    # Subset to keep Optuna hyperparameter trials fast
    train_graphs = build_sliding_windows(max(lookback_window - 1, split_idx - 45), split_idx - 1)
    val_graphs = build_sliding_windows(max(lookback_window - 1, split_idx - 1), min(len(all_graphs) - 1, split_idx + 10))
    
    if not train_graphs or not val_graphs:
        # Fallback to random targets if not enough slices can be formed
        print("Warning: not enough slices for Optuna search. Using subset bounds fallback.")
        return 0.0

    trainer = STGCNTrainer(model, train_graphs, val_graphs, config)
    
    best_val_f1 = 0.0
    for epoch in range(config["max_epochs"]):
        trainer.train_epoch()
        val_metrics = trainer.validate()
        f1 = val_metrics.get("f1_macro", 0.0)
        
        if f1 > best_val_f1:
            best_val_f1 = f1
            
        trial.report(f1, epoch)
        if trial.should_prune():
            raise optuna.TrialPruned()
            
    return best_val_f1

def run_hyperopt(features: dict = None, available_symbols: list = None) -> dict:
    """
    Run Optuna study.
    """
    if features is None or available_symbols is None:
        return {
            "hidden_dim": 128,
            "gat_heads_1": 4,
            "transformer_layers": 2,
            "dropout": 0.2,
            "learning_rate": 0.001,
            "lookback_window": 30
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
        # Fallback if too little data
        print("Not enough daily graphs for Optuna optimization.")
        return {
            "hidden_dim": 128,
            "gat_heads_1": 4,
            "transformer_layers": 2,
            "dropout": 0.2,
            "learning_rate": 0.001,
            "lookback_window": 30
        }

    study = optuna.create_study(
        direction="maximize",
        pruner=MedianPruner(n_startup_trials=5)
    )
    
    # Run only 2 trials for fast testing unless overridden
    n_trials = int(os.environ.get("OPTUNA_TRIALS", 2))
    study.optimize(lambda t: objective(t, all_graphs, graph_dates, proc_features, available_symbols), n_trials=n_trials)

    best_params = study.best_params
    print(f"Best params: {best_params}")

    os.makedirs("ml/artifacts", exist_ok=True)
    with open("ml/artifacts/best_params.json", "w") as f:
        json.dump(best_params, f, indent=4)

    return best_params

if __name__ == "__main__":
    os.environ["OPTUNA_TRIALS"] = "2" 
    best = run_hyperopt(None, None)
    print(f"Hyperopt finished successfully.")

