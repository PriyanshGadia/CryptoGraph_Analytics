import os
import torch
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

def main():
    # Resolve latest run artifacts
    artifacts_dir = Path("ml/artifacts")
    runs_dir = artifacts_dir / "runs"
    latest_runs = sorted(runs_dir.glob("2026*"))
    if not latest_runs:
        latest_run = artifacts_dir
    else:
        latest_run = latest_runs[-1]

    import argparse
    parser = argparse.ArgumentParser(description="Plot training history from checkpoints.")
    parser.add_argument("--run-dir", type=str, default=str(latest_run), help="Path to run directory containing checkpoint_last.pt")
    parser.add_argument("--output", type=str, default="ml/artifacts/training_history.png", help="Output path for the plot")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    checkpoint_path = run_dir / "checkpoint_last.pt"
    if not checkpoint_path.exists():
        checkpoint_path = artifacts_dir / "checkpoint_last.pt"
        if not checkpoint_path.exists():
            pts = list(run_dir.glob("*.pt"))
            if pts:
                checkpoint_path = pts[0]
            else:
                raise FileNotFoundError(f"No checkpoint file found in {run_dir}")

    print(f"Loading checkpoint from: {checkpoint_path}")
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    history = ckpt.get("history", {})

    if not history:
        print("Warning: history is empty in the checkpoint.")
        best_path = run_dir / "best_model.pt"
        if best_path.exists():
            ckpt = torch.load(best_path, map_location="cpu", weights_only=False)
            history = ckpt.get("history", {})

    epochs = list(range(1, len(history.get("train_loss", [])) + 1))
    if not epochs:
        print("No history metrics found to plot.")
        exit(0)

    # Set premium dark Slate styling
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5), facecolor='#0F172A')

    for ax in axes:
        ax.set_facecolor('#1E293B')
        ax.grid(True, color='#334155', linestyle='--', alpha=0.5)
        ax.tick_params(colors='#94A3B8', labelsize=10)
        ax.xaxis.label.set_color('#94A3B8')
        ax.yaxis.label.set_color('#94A3B8')

    # Subplot 0: Training & Validation Loss
    train_loss = history.get("train_loss", [])
    val_loss = history.get("val_loss", [])
    axes[0].plot(epochs, train_loss, color="#6366F1", lw=2.5, label="Train Loss")
    if val_loss:
        axes[0].plot(epochs, val_loss, color="#10B981", lw=2.5, label="Val Loss")
    axes[0].set_title("Loss Progression", fontsize=14, fontweight="bold", color="#F8FAFC", pad=12)
    axes[0].set_xlabel("Epochs")
    axes[0].set_ylabel("Loss Value")
    axes[0].legend(facecolor='#1E293B', edgecolor='#334155', labelcolor='#F8FAFC')

    # Subplot 1: Validation R2 Score
    val_r2 = history.get("val_r2", [])
    if val_r2:
        axes[1].plot(epochs, val_r2, color="#3B82F6", lw=2.5, label="Val R²")
        best_r2_idx = np.argmax(val_r2)
        best_r2 = val_r2[best_r2_idx]
        axes[1].scatter(best_r2_idx + 1, best_r2, color="#EF4444", s=80, zorder=5, 
                         label=f"Best R²: {best_r2:.4f} (Ep {best_r2_idx + 1})")
        
        # Draw horizontal baseline at 0.0
        axes[1].axhline(y=0.0, color="#EF4444", linestyle="--", alpha=0.6, lw=1.5, label="Baseline (Mean)")
        axes[1].set_title("Validation R² Progression", fontsize=14, fontweight="bold", color="#F8FAFC", pad=12)
        axes[1].set_xlabel("Epochs")
        axes[1].set_ylabel("R² Score")
        axes[1].legend(facecolor='#1E293B', edgecolor='#334155', labelcolor='#F8FAFC')

    # Subplot 2: Learning Rate & Predictor Variance (pred_std)
    lrs = history.get("lr", [])
    val_mean_pred_std = history.get("val_mean_pred_std", [])

    color_lr = "#EC4899"
    color_std = "#F59E0B"

    # Primary Y-axis: LR
    ax2_primary = axes[2]
    if lrs:
        ax2_primary.plot(epochs, lrs, color=color_lr, lw=2.5, label="Learning Rate")
        ax2_primary.set_ylabel("Learning Rate", color=color_lr)
        ax2_primary.tick_params(axis='y', labelcolor=color_lr)

    # Secondary Y-axis: prediction std
    if val_mean_pred_std:
        ax2_sec = ax2_primary.twinx()
        ax2_sec.plot(epochs, val_mean_pred_std, color=color_std, lw=2.0, linestyle="--", label="Pred Std")
        ax2_sec.set_ylabel("Validation Pred Std", color=color_std)
        ax2_sec.tick_params(axis='y', labelcolor=color_std)
        ax2_sec.grid(False) # avoid double grids

    axes[2].set_title("Optimizer & Variance States", fontsize=14, fontweight="bold", color="#F8FAFC", pad=12)
    axes[2].set_xlabel("Epochs")

    # Setup legend for dual axis
    lines1, labels1 = ax2_primary.get_legend_handles_labels()
    if val_mean_pred_std:
        lines2, labels2 = ax2_sec.get_legend_handles_labels()
        ax2_primary.legend(lines1 + lines2, labels1 + labels2, facecolor='#1E293B', edgecolor='#334155', labelcolor='#F8FAFC', loc="upper left")
    else:
        ax2_primary.legend(facecolor='#1E293B', edgecolor='#334155', labelcolor='#F8FAFC')

    plt.tight_layout()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, facecolor=fig.get_facecolor(), edgecolor='none')
    print(f"Plot successfully saved to: {output_path}")

if __name__ == "__main__":
    main()
