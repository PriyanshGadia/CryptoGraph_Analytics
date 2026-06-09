import os
from pathlib import Path
from dotenv import load_dotenv
import wandb

class WandbTracker:
    """Centralised W&B logging interface."""

    def __init__(self, config: dict):
        """Login with WANDB_API_KEY from ml/.env, init project stgcn-crypto-forecasting."""
        load_dotenv(Path("ml/.env"))
        wandb.login(key=os.getenv("WANDB_API_KEY"))
        self.run = wandb.init(
            entity="jakshat557-akshat-ai-solutions",
            project="stgcn-crypto-forecasting",
            config=config
        )

    def log_epoch(self, epoch: int, metrics: dict) -> None:
        """Log all training metrics for one epoch with step=epoch."""
        wandb.log(metrics, step=epoch)

    def log_confusion_matrix(
        self, y_true: list, y_pred: list, class_names: list
    ) -> None:
        """Log confusion matrix as wandb.plot.confusion_matrix."""
        wandb.log({
            "confusion_matrix": wandb.plot.confusion_matrix(
                preds=y_pred,
                y_true=y_true,
                class_names=class_names
            )
        })

    def log_model_artifact(self, path: str) -> None:
        """Upload model checkpoint file as W&B artifact type='model'."""
        artifact = wandb.Artifact("stgcn_model", type="model")
        artifact.add_file(path)
        self.run.log_artifact(artifact)

    def log_graph_snapshot(self, date: str, graph_summary: dict) -> None:
        """Log graph stats as a row in a W&B Table. Columns from graph_summary keys."""
        # Check if table exists in current run, else create
        if not hasattr(self, "graph_table"):
            self.graph_table = wandb.Table(columns=["date"] + list(graph_summary.keys()))
        
        row = [date] + list(graph_summary.values())
        self.graph_table.add_data(*row)
        
        wandb.log({"graph_snapshots": self.graph_table})

    def log_backtest_results(self, results: dict) -> None:
        """Log all finance metrics from backtester to W&B summary."""
        for key, value in results.items():
            self.run.summary[key] = value

    def finish(self) -> None:
        wandb.finish()
