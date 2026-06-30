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

from ml.data.feature_store.store import FeatureStore
from ml.graph.graph_builder import DynamicGraphBuilder
from ml.models.stgcn import STGCNModel
from ml.training.trainer import STGCNTrainer
from ml.evaluation.explainability import explain_all_assets
from ml.hyperopt.optuna_search import run_hyperopt

# Ensure artifacts directory exists
os.makedirs("ml/artifacts", exist_ok=True)

SYMBOLS = [
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT",
    "MATIC", "UNI", "ATOM", "LTC", "BCH", "XLM", "ALGO", "VET", "FIL", "TRX",
    "NEAR", "SAND", "MANA", "AXS", "THETA", "XMR", "EOS", "AAVE", "MKR", "COMP",
    "SNX", "YFI", "SUSHI", "CRV", "BAL", "ZRX", "REN", "LRC", "BAT", "ZEC",
    "DASH", "WAVES", "ICX", "QTUM", "ONT", "ZIL", "IOTA", "DGB", "1INCH", "FTM",
]

def main():
    # CPU usage constraints for Intel i3 compatibility
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)

    print("▶ Step 1: Loading features from FeatureStore...")
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

    print("\n▶ Step 2: Running Optuna hyperparameter search...")
    # This will save ml/artifacts/best_params.json
    # Pass features to hyperopt if we update optuna_search to accept it
    # For now, we'll run the default implementation
    best_params = run_hyperopt(features, available_symbols)
    
    print("\n▶ Step 3: Loading best hyperparameters...")
    best_params["max_epochs"] = 10
    print(f"Best Params: {best_params}")
    
    print("\n▶ Step 4: Training STGCNModel with best hyperparameters...")
    
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
    
    lookback_window = best_params.get("lookback_window", 30)
    
    # Chronological split at 80% mark
    split_idx = int(len(all_graphs) * 0.8)
    
    # Ensure we have enough data
    if len(all_graphs) < lookback_window + 5:
        print("Not enough graphs built to form sliding windows.")
        return
        
    print(f"Building sliding window datasets (lookback={lookback_window})...")
    
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
            # The input sequence is lookback_window graphs ending at idx
            input_seq = all_graphs[idx - lookback_window + 1 : idx + 1]
            target_date = graph_dates[idx + 1] # Target is the next day's label
            
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

    train_graphs = build_sliding_windows(lookback_window, split_idx - 1)
    val_graphs = build_sliding_windows(split_idx, len(all_graphs) - 2)
    
    print(f"Dataset summary: {len(train_graphs)} train samples, {len(val_graphs)} val samples.")
    
    # Calculate direction class counts in train dataset for inverse frequency weights
    dir_counts = [0] * 5
    for _, dir_labels, _, _ in train_graphs:
        for val in dir_labels.tolist():
            if 0 <= val < 5:
                dir_counts[val] += 1
    if any(c == 0 for c in dir_counts):
        dir_counts = [max(1, c) for c in dir_counts]
    best_params["direction_class_counts"] = dir_counts
    print(f"Computed training set class distribution: {dir_counts}")
    
    N = len(available_symbols)
    model = STGCNModel(
        in_features=24,
        hidden_dim=best_params.get("hidden_dim", 128),
        dropout=best_params.get("dropout", 0.2)
    )
    
    trainer = STGCNTrainer(model, train_graphs, val_graphs, best_params)
    trainer.fit()
    
    print("\n▶ Step 4.5: Calibrating model probabilities using Temperature Scaling...")
    # Temperature scaling grid search to minimize validation set cross-entropy (NLL)
    best_temp = 1.0
    best_nll = float('inf')
    model.eval()
    
    all_logits = []
    all_targets = []
    with torch.no_grad():
        for graph_seq, dir_labels, _, _ in val_graphs:
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
                
    print(f"Optimal probability calibration temperature: {best_temp:.2f} (Val NLL: {best_nll:.4f})")
    model.config["temperature"] = best_temp
    
    print("\n▶ Step 5: Computing Captum explainability...")
    feature_names = [
        "open", "high", "low", "close", "volume", 
        "rsi_14", "macd", "macd_signal", "atr_14", "bb_width",
        "returns_1d", "returns_7d", "volatility_7d", 
        "sentiment_score", "fear_greed_norm", "community_score", "public_interest", 
        "sentiment_rolling_3d", "sentiment_momentum", "market_cap_usd",
        "fed_rate", "cpi", "inflation", "vix"
    ]
    graph_sequences_dict = {sym: val_graphs[-1][0] for sym in available_symbols}
    explain_all_assets(model, graph_sequences_dict, feature_names, db_session=None)

    print("\n▶ Step 6: Registering model in SQLite...")
    # Save the model using model.save so config is saved correctly
    model.save("ml/artifacts/best_model.pt")

    print("\n🎉 Training pipeline complete")

if __name__ == "__main__":
    main()

