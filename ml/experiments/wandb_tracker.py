import os
from pathlib import Path

# wandb is optional — fall back to a no-op tracker if not installed or key is absent
try:
    import wandb as _wandb
    _WANDB_AVAILABLE = True
except ImportError:
    _wandb = None  # type: ignore
    _WANDB_AVAILABLE = False


class WandbTracker:
    """Centralised W&B logging interface with graceful no-op fallback."""

    def __init__(self, config: dict):
        """Login with wandb_api_key from SQLite app_settings; no-op if unavailable."""
        self.run = None
        self._enabled = False

        if not _WANDB_AVAILABLE:
            print("[WandbTracker] wandb not installed — logging disabled.")
            return

        # Read key from SQLite app_settings (no .env)
        api_key = None
        try:
            import sqlite3
            from pathlib import Path as _Path
            _db_candidates = [
                _Path(__file__).resolve().parent.parent.parent / "backend" / "cryptograph.db",
                _Path(__file__).resolve().parent.parent.parent / "cryptograph.db",
            ]
            _db = next((p for p in _db_candidates if p.exists()), None)
            if _db:
                conn = sqlite3.connect(str(_db))
                row = conn.execute(
                    "SELECT setting_value FROM app_settings WHERE setting_key = 'wandb_api_key'"
                ).fetchone()
                conn.close()
                if row and row[0]:
                    api_key = row[0]
        except Exception:
            pass

        try:
            _wandb.login(key=api_key)  # key=None → uses WANDB_API_KEY env var if set
            self.run = _wandb.init(
                entity="jakshat557-akshat-ai-solutions",
                project="stgcn-crypto-forecasting",
                config=config,
                mode=config.get("wandb_mode", "online"),  # pass "disabled" to suppress
            )
            self._enabled = True
        except Exception as exc:
            print(f"[WandbTracker] W&B init failed ({exc}) — logging disabled.")

    def log_epoch(self, epoch: int, metrics: dict) -> None:
        if self._enabled:
            _wandb.log(metrics, step=epoch)

    def log_confusion_matrix(self, y_true: list, y_pred: list, class_names: list) -> None:
        if self._enabled:
            _wandb.log({
                "confusion_matrix": _wandb.plot.confusion_matrix(
                    preds=y_pred, y_true=y_true, class_names=class_names
                )
            })

    def log_model_artifact(self, path: str) -> None:
        if self._enabled and self.run and path:
            try:
                artifact = _wandb.Artifact("stgcn_model", type="model")
                artifact.add_file(path)
                self.run.log_artifact(artifact)
            except Exception as exc:
                print(f"[WandbTracker] artifact upload failed: {exc}")

    def log_graph_snapshot(self, date: str, graph_summary: dict) -> None:
        if not self._enabled:
            return
        if not hasattr(self, "graph_table"):
            self.graph_table = _wandb.Table(columns=["date"] + list(graph_summary.keys()))
        self.graph_table.add_data(date, *graph_summary.values())
        _wandb.log({"graph_snapshots": self.graph_table})

    def log_backtest_results(self, results: dict) -> None:
        if self._enabled and self.run:
            for key, value in results.items():
                self.run.summary[key] = value

    def finish(self) -> None:
        if self._enabled:
            try:
                _wandb.finish()
            except Exception:
                pass
