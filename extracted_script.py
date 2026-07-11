import os
import sys
import torch
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# Add project root to path
sys.path.append("/kaggle/working/CryptoGraph_Analytics")

from ml.pipelines.training_pipeline_enterprise import (
    load_data,
    TrainingConfig,
    EnterpriseSTGCNModel,
    WindowedGraphDataset,
    graph_collate_fn,
)
from ml.evaluation.finance_metrics import compute_all_finance_metrics
from ml.scripts.seed_assets_top100 import TOP_100_SYMBOLS

# 1. Config & Data Loader Setup
config = TrainingConfig()
config.hidden_dim = 64       # Matches the regularized training model dim (64)
config.lookback_days = 10    # Matches the trained model lookback window (10)
config.batch_size = 8
config.use_sam = False
config.num_workers = 0       # Keep to 0 to prevent PyG CPU-GPU serialization bottlenecks

# Use all 100 assets configured in the authoritative list
symbols = list(TOP_100_SYMBOLS)

print(f"Loading test data for {len(symbols)} assets...")
dataset_tuple = load_data(config, symbols, rank=0, is_distributed=False)
(all_graphs, target_returns, target_masks, graph_dates, available_symbols, scale_map) = dataset_tuple

# Rebuild test dataloader using PyTorch native DataLoader and custom collate function
from torch.utils.data import DataLoader

n = len(all_graphs)
train_end = int(n * 0.70)
val_end = int(n * 0.85)

test_dataset = WindowedGraphDataset(
    all_graphs, target_returns, target_masks, 
    config.lookback_days, config.forecast_horizon, 
    start_idx=val_end, end_idx=n
)
test_loader = DataLoader(
    test_dataset, 
    batch_size=config.batch_size, 
    shuffle=False, 
    collate_fn=graph_collate_fn
)

# 2. Load Snapshots & Predict
latest_run = sorted(Path("/kaggle/working/CryptoGraph_Analytics/ml/artifacts/runs").glob("2026*"))[-1]
snapshots = sorted(latest_run.glob("snapshot_epoch*.pt"))
print(f"Found {len(snapshots)} snapshots for ensembling in: {latest_run.name}")

models = []
for snap in snapshots:
    m = EnterpriseSTGCNModel.load(str(snap))
    m.to("cuda" if torch.cuda.is_available() else "cpu")
    m.eval()
    models.append(m)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
all_preds, all_targets, all_masks = [], [], []

with torch.no_grad():
    for seqs, targs, msks in test_loader:
        # Move sequences and inputs to correct device (PyG Batch-safe)
        from torch_geometric.data import Batch
        if isinstance(seqs, Batch):
            seqs_dev = seqs.to(device)
        else:
            seqs_dev = [[g.to(device) for g in seq] for seq in seqs]

        # Average predictions across snapshots
        batch_preds = []
        for m in models:
            pred = m(seqs_dev)
            batch_preds.append(pred.cpu().numpy())  # Keep entire batch [B, N]
            
        avg_pred = np.mean(batch_preds, axis=0)
        all_preds.append(avg_pred)
        all_targets.append(targs.numpy())
        all_masks.append(msks.numpy())

preds = np.concatenate(all_preds, axis=0)
targets = np.concatenate(all_targets, axis=0)
masks = np.concatenate(all_masks, axis=0)

# 3. Simulate Long/Short Strategy
# Denormalize predictions and targets using scale_map
for idx, sym in enumerate(available_symbols):
    scale = scale_map.get(sym, 1.0)
    preds[:, idx] *= scale
    targets[:, idx] *= scale

# Build cumulative returns series
# Equi-weighted daily asset returns for Long/Short signals
signals = np.zeros_like(preds)
for t in range(len(preds)):
    valid_idx = np.where(masks[t] == 1)[0]
    if len(valid_idx) < 2:
        continue
    t_preds = preds[t, valid_idx]
    median_pred = np.median(t_preds)
    
    # Calculate sizes to prevent division by zero
    long_mask = t_preds > median_pred
    short_mask = t_preds <= median_pred
    num_long = np.sum(long_mask)
    num_short = np.sum(short_mask)
    
    if num_long > 0:
        signals[t, valid_idx[long_mask]] = 1.0 / num_long
    if num_short > 0:
        signals[t, valid_idx[short_mask]] = -1.0 / num_short

# Compute rebalancing transaction fees (10bps fee per trade change)
trade_diff = np.abs(signals[1:] - signals[:-1])
fees = 0.0010 * np.sum(trade_diff, axis=1)
fees = np.insert(fees, 0, 0.0)  # Prepend 0.0 for the first day (no initial trade change)

daily_returns = np.sum(signals * targets, axis=1) - fees
cum_returns = np.cumprod(1.0 + daily_returns) - 1.0

# Compute strategy metrics directly from returns series
daily_returns_series = pd.Series(daily_returns)
strat_metrics = compute_all_finance_metrics(daily_returns_series)

# Benchmark (BTC Buy-and-Hold)
btc_idx = available_symbols.index("BTC")
btc_returns = targets[:, btc_idx]
btc_cum = np.cumprod(1.0 + btc_returns) - 1.0

# 4. Plot Backtest & Feature Importance
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 7), facecolor='#0F172A')

for ax in [ax1, ax2]:
    ax.set_facecolor('#1E293B')
    ax.grid(True, color='#334155', linestyle='--', alpha=0.5)
    ax.tick_params(colors='#94A3B8', labelsize=10)
    ax.xaxis.label.set_color('#94A3B8')
    ax.yaxis.label.set_color('#94A3B8')

# Backtest chart
ax1.plot(cum_returns * 100, label="ST-GCN Ensemble Strategy (Net of Fees)", color="#6366F1", lw=2.5)
ax1.plot(btc_cum * 100, label="BTC Benchmark (Buy & Hold)", color="#F59E0B", lw=1.5, alpha=0.8)
ax1.set_title("Strategy Cumulative Returns (Test Set)", fontsize=14, fontweight="bold", color="#F8FAFC", pad=12)
ax1.set_ylabel("Cumulative Performance (%)")
ax1.set_xlabel("Test Days")
ax1.legend(facecolor='#1E293B', edgecolor='#334155', labelcolor='#F8FAFC', fontsize=11)

# Feature Importance chart (Values fetched from latest run)
importances = [
    0.000515, 0.001032, 0.000192, 0.000663, 0.000578, 0.000908, 0.001212, -0.000143,
    0.001239, 0.000368, 0.000099, 0.000268, 0.000299, 0.000533, 0.000288, 0.000386,
    0.000832, 0.000130, 0.000306, 0.001359, 0.000547, 0.000616, 0.000073, 0.000213
]
features = [
    "open", "high", "low", "close", "volume", "rsi_14", "macd", "macd_signal", "atr_14", "bb_width",
    "returns_1d", "returns_7d", "volatility_7d", "sentiment_score", "fear_greed", "community",
    "interest", "sent_roll_3d", "sent_mom", "market_cap", "fed_rate", "cpi", "inflation", "vix"
]

y_pos = np.arange(len(features))
sorted_idx = np.argsort(importances)

ax2.barh(y_pos, np.array(importances)[sorted_idx], color="#10B981")
ax2.set_yticks(y_pos)
ax2.set_yticklabels(np.array(features)[sorted_idx], fontsize=10, color='#94A3B8')
ax2.set_title("Permutation Feature Importance Attributions", fontsize=14, fontweight="bold", color="#F8FAFC", pad=12)
ax2.set_xlabel("Mean Absolute Error Delta")

plt.tight_layout()
plt.show()

# Print detailed results
print("="*60)
print("ENSEMBLE PORTFOLIO BACKTEST SUMMARY")
print("="*60)
for k, v in strat_metrics.items():
    print(f"{k:<30}: {v:.6f}")
print("="*60)
