"""
Deterministic Historical Predictions Seeder.
Uses the PyTorch ST-GCN inference engine to generate authentic, non-random historical predictions.
"""
import sys
import os
from pathlib import Path

# Add root folder to sys.path
root_dir = Path(__file__).resolve().parents[2]
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from ml.pipelines.inference_pipeline import run_inference_pipeline

def populate_historical_predictions():
    print("Running PyTorch ST-GCN Inference Engine to populate database with deterministic predictions...")
    res = run_inference_pipeline()
    print(f"ST-GCN Inference complete. Result: {res}")

if __name__ == "__main__":
    populate_historical_predictions()

