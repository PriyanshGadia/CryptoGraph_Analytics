import sys
import os
import json
import argparse
from pathlib import Path

# Add root directory to python path
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))
if str(root_dir / "backend") not in sys.path:
    sys.path.append(str(root_dir / "backend"))

# Force low resource usage configuration
os.environ["IS_ML_WORKER"] = "true"
os.environ["LOW_MEM"] = "false"  # Let the worker run the actual models
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

def run_inference_task():
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    
    from ml.pipelines.inference_pipeline import run_inference
    result = run_inference()
    print(json.dumps(result))

def run_forecast_task(prices_json, dates_json):
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    
    import pandas as pd
    from ml.models.forecast_model import run_ensemble_forecast
    
    prices_raw = json.loads(prices_json)
    dates_raw = json.loads(dates_json)
    
    prices = pd.Series(prices_raw)
    dates = pd.Series(pd.to_datetime(dates_raw))
    
    result = run_ensemble_forecast(prices, dates, 30)
    print(json.dumps(result))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=str, required=True, choices=["inference", "forecast"])
    parser.add_argument("--prices", type=str, default="[]")
    parser.add_argument("--dates", type=str, default="[]")
    args = parser.parse_args()
    
    if args.task == "inference":
        run_inference_task()
    elif args.task == "forecast":
        run_forecast_task(args.prices, args.dates)
