"""
Autonomous MLOps Retraining Pipeline (Self-Healing AI).
Prevents Model Decay by fetching the latest OHLCV data, automatically retraining
the PyTorch ST-GCN tensors, and rolling forward weights if validation loss improves.
"""

import os
import torch
import torch.nn as nn
from datetime import datetime, timedelta, timezone
from app.db.database import SessionLocal
from ml.data.feature_store.store import FeatureStore
from ml.graph.graph_builder import DynamicGraphBuilder
from ml.models.stgcn import STGCNModel
from ml.pipelines.training_pipeline import main as run_train_main, SYMBOLS

class MLOpsPipeline:
    def __init__(self):
        self.model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "ml", "artifacts", "best_model.pt"))
        self.backup_path = self.model_path + ".backup"
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
    def evaluate_saved_model(self, model_path, val_graphs) -> float:
        """Calculates the validation loss of a given model checkpoint file."""
        if not os.path.exists(model_path):
            print(f"[MLOps] Model path {model_path} does not exist.")
            return float('inf')
        try:
            model = STGCNModel.load(model_path, map_location=self.device)
            model.eval()
            criterion = nn.CrossEntropyLoss()
            total_loss = 0.0
            with torch.no_grad():
                for graph_seq, dir_labels, vol_labels, returns in val_graphs:
                    graph_seq = [g.to(self.device) for g in graph_seq]
                    dir_labels = dir_labels.to(self.device)
                    vol_labels = vol_labels.to(self.device)
                    dir_logits, vol_logits = model(graph_seq)
                    loss_dir = criterion(dir_logits, dir_labels)
                    loss_vol = criterion(vol_logits, vol_labels)
                    total_loss += (loss_dir.item() + loss_vol.item())
            return total_loss / max(1, len(val_graphs))
        except Exception as e:
            print(f"[MLOps] Error evaluating model at {model_path}: {e}")
            return float('inf')
            
    def run_weekly_retraining(self):
        """
        The core CI/CD machine learning loop.
        1. Fetch new data
        2. Evaluate current model
        3. Train a candidate model
        4. Hot-swap weights if candidate wins.
        """
        print(f"[{datetime.now(timezone.utc).isoformat()}] Starting Autonomous MLOps Retraining...")
        
        # Load validation dataset to compare performance
        store = FeatureStore()
        now = datetime.now(timezone.utc)
        # Load past 60 days
        start_date = (now - timedelta(days=60)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")
        
        features = store.load_node_features(start_date, end_date, SYMBOLS, expected_features=24)
        available_symbols = [s for s in SYMBOLS if s in features and not features[s].empty]
        if not available_symbols:
            print("[MLOps] Insufficient features loaded. Retraining aborted.")
            return
            
        print(f"[MLOps] Loaded features for validation evaluation.")
        
        # Build sliding windows for evaluation
        builder = DynamicGraphBuilder()
        all_graphs, graph_dates = builder.build_dynamic_graph_sequence(features, available_symbols)
        
        # Use lookback of 14 for evaluation
        lookback_window = 14
        
        # Get active assets features
        proc_features = {}
        for sym in available_symbols:
            df = features[sym].copy()
            df.index = pd.to_datetime(df.index).tz_localize(None)
            proc_features[sym] = df
            
        def classify_direction(ret):
            if ret <= -0.03: return 0
            if ret <= -0.01: return 1
            if ret < 0.01: return 2
            if ret < 0.03: return 3
            return 4

        def classify_volatility(vol):
            if vol <= 0.02: return 0
            if vol <= 0.05: return 1
            if vol <= 0.10: return 2
            return 3
            
        def build_val_windows(start_idx, end_idx):
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

        # Build validation set (most recent 15 samples)
        val_graphs = build_val_windows(max(lookback_window - 1, len(all_graphs) - 16), len(all_graphs) - 1)
        
        # Calculate current production loss
        production_loss = self.evaluate_saved_model(self.model_path, val_graphs)
        print(f"[MLOps] Current Production model validation loss: {production_loss:.6f}")
        
        # Back up existing best_model.pt
        temp_backup = self.model_path + ".temp"
        if os.path.exists(self.model_path):
            import shutil
            shutil.copy2(self.model_path, temp_backup)
            
        # Run real training pipeline to produce new best_model.pt
        try:
            print("[MLOps] Executing training pipeline...")
            run_train_main()
            
            # Evaluate new model candidate
            candidate_loss = self.evaluate_saved_model(self.model_path, val_graphs)
            print(f"[MLOps] Trained Candidate model validation loss: {candidate_loss:.6f}")
            
            if candidate_loss < production_loss:
                print("[MLOps] Candidate outperforms production! Hot-swapping model.")
                if os.path.exists(temp_backup):
                    if os.path.exists(self.backup_path):
                        os.remove(self.backup_path)
                    os.rename(temp_backup, self.backup_path)
                print("[MLOps] MLOps Pipeline Complete. Neural core evolved successfully.")
            else:
                print("[MLOps] Candidate model rejected. Reverting best_model to production version.")
                if os.path.exists(temp_backup):
                    if os.path.exists(self.model_path):
                        os.remove(self.model_path)
                    os.rename(temp_backup, self.model_path)
                else:
                    print("[MLOps] Warning: Production backup not found to revert.")
        except Exception as e:
            print(f"[MLOps] Training pipeline execution failed: {e}")
            if os.path.exists(temp_backup):
                if os.path.exists(self.model_path):
                    os.remove(self.model_path)
                os.rename(temp_backup, self.model_path)
                print("[MLOps] Reverted to production model after failure.")
        finally:
            if os.path.exists(temp_backup):
                os.remove(temp_backup)

if __name__ == "__main__":
    import pandas as pd
    pipeline = MLOpsPipeline()
    pipeline.run_weekly_retraining()
