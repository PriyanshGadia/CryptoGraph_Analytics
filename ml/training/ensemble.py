"""
Snapshot Ensemble Inference Engine.

Loads multiple trained model checkpoints (e.g., top-k checkpoints or SWA/snapshot models)
and averages their predicted probability distributions to form a highly robust ensemble
with low variance and improved generalized accuracy.
"""

import os
import glob
import torch
import torch.nn as nn
from typing import List, Tuple
from torch import Tensor

from ml.models.stgcn import STGCNModel

class EnsembleSTGCNModel(nn.Module):
    """Ensemble model that wraps multiple STGCNModel checkpoints."""

    def __init__(self, checkpoint_paths: List[str], device: str = "cpu"):
        super().__init__()
        self.device = device
        self.models: List[STGCNModel] = []
        
        for path in checkpoint_paths:
            if os.path.exists(path):
                print(f"[Ensemble] Loading model checkpoint: {path}")
                model = STGCNModel.load(path, map_location=device)
                model.eval()
                self.models.append(model)
                
        if not self.models:
            raise ValueError(f"No valid checkpoints found in provided paths: {checkpoint_paths}")
        print(f"[Ensemble] Initialized ensemble with {len(self.models)} models.")

    def forward(self, graph_sequence: list) -> Tuple[Tensor, Tensor]:
        """Runs forward pass across all sub-models and averages their softmax probabilities.

        Returns
        -------
        dir_probs : Tensor
            Averaged direction probabilities shape (N, num_classes)
        vol_probs : Tensor
            Averaged volatility probabilities shape (N, num_volatility_classes)
        """
        all_dir_probs = []
        all_vol_probs = []

        with torch.no_grad():
            for model in self.models:
                dir_logits, vol_logits = model(graph_sequence)
                
                # Temperature scaling is applied if stored in model config
                temp = model.config.get("temperature", 1.0)
                
                dir_probs = torch.softmax(dir_logits / temp, dim=-1)
                vol_probs = torch.softmax(vol_logits, dim=-1)
                
                all_dir_probs.append(dir_probs)
                all_vol_probs.append(vol_probs)

        # Average probabilities
        avg_dir_probs = torch.stack(all_dir_probs, dim=0).mean(dim=0)
        avg_vol_probs = torch.stack(all_vol_probs, dim=0).mean(dim=0)
        
        return avg_dir_probs, avg_vol_probs

def get_ensemble_model(checkpoint_dir: str = "ml/artifacts", limit: int = 3, device: str = "cpu") -> EnsembleSTGCNModel:
    """Discovers best score checkpoints and returns an EnsembleSTGCNModel."""
    # Find checkpoint files
    checkpoint_files = glob.glob(os.path.join(checkpoint_dir, "checkpoint_epoch_*_score_*.pt"))
    
    # Parse scores from filename: e.g. checkpoint_epoch_10_score_0.4502.pt
    scored_files = []
    for f in checkpoint_files:
        try:
            basename = os.path.basename(f)
            # split by score_ and .pt
            parts = basename.split("score_")
            if len(parts) > 1:
                score_val = float(parts[1].replace(".pt", ""))
                scored_files.append((score_val, f))
        except Exception:
            pass
            
    # Add best_model.pt to the list with high score so it is always included if exists
    best_model_path = os.path.join(checkpoint_dir, "best_model.pt")
    if os.path.exists(best_model_path):
        scored_files.append((999.0, best_model_path))

    # Sort descending by score
    scored_files.sort(key=lambda x: x[0], reverse=True)
    
    # Select top-k unique paths
    seen_paths = set()
    selected_paths = []
    for _, path in scored_files:
        canonical_path = os.path.abspath(path)
        if canonical_path not in seen_paths:
            seen_paths.add(canonical_path)
            selected_paths.append(path)
            if len(selected_paths) >= limit:
                break
                
    if not selected_paths:
        # Fallback to whatever is in best_model.pt or target path
        selected_paths = [best_model_path]
        
    return EnsembleSTGCNModel(selected_paths, device=device)
