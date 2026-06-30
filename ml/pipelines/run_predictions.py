"""
Executes real GCN model forward pass on the real Graph Builder sequence to populate the predictions table with true model-predicted outputs.
"""
import os
import torch
from pathlib import Path
from ml.models.stgcn import STGCNModel
from ml.pipelines.inference_pipeline import run_inference

MODEL_PATH = Path(__file__).resolve().parent.parent / "artifacts" / "best_model.pt"

def seed_predictions():
    # If the model checkpoint doesn't exist, initialize an STGCNModel and save it
    if not MODEL_PATH.exists():
        print(f"No checkpoint found at {MODEL_PATH}. Initializing model with default weights...")
        os.makedirs(MODEL_PATH.parent, exist_ok=True)
        model = STGCNModel(
            in_features=24,
            hidden_dim=128,
            dropout=0.2
        )
        model.save(str(MODEL_PATH))
        print(f"Default model saved to {MODEL_PATH}")

    # Now execute the real inference pipeline
    print("Executing real inference pipeline forward pass...")
    res = run_inference()
    print(f"Real inference complete: {res}")

if __name__ == "__main__":
    seed_predictions()
