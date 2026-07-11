"""
training_monitor.py — CryptoGraph Enterprise STGCN Training Monitor
====================================================================
Run this in a SEPARATE Kaggle cell (or terminal) alongside the training script.
It tails the log file, computes rolling convergence analytics, detects
overfitting in real-time, and writes signal files that the trainer polls:

    Signal files (written to ARTIFACTS_DIR / ml/artifacts/):
        lr_reset.flag       -> trainer resets LR to learning_rate and clears patience
        stop_training.flag  -> trainer stops gracefully at next epoch boundary

Usage (Kaggle):
    import subprocess
    proc = subprocess.Popen(
        ["python", "CryptoGraph_Analytics/ml/pipelines/training_monitor.py",
         "--log", "/kaggle/working/logs.txt",
         "--signal-dir", "/kaggle/working/CryptoGraph_Analytics/CryptoGraph_Analytics/CryptoGraph_Analytics/CryptoGraph_Analytics/ml/artifacts"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    for line in proc.stdout:
        print(line, end="")

Usage (local):
    python ml/pipelines/training_monitor.py
"""

import argparse
import os
import re
import sys
import time
from collections import deque
from pathlib import Path
from typing import Optional

# ─── Defaults ────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_LOG = _REPO_ROOT / "logs.txt"
_DEFAULT_SIGNAL_DIR = _REPO_ROOT / "ml" / "artifacts"

# ─── ANSI colours (stripped on non-TTY) ──────────────────────────────────────
def _c(code: str, text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"

RED    = lambda t: _c("31;1", t)
YELLOW = lambda t: _c("33;1", t)
GREEN  = lambda t: _c("32;1", t)
CYAN   = lambda t: _c("36;1", t)
BOLD   = lambda t: _c("1",    t)
DIM    = lambda t: _c("2",    t)

# ─── Regex patterns ───────────────────────────────────────────────────────────
_EPOCH_RE  = re.compile(
    r"Epoch (\d+)\s*\|.*Train loss:\s*([\d.]+).*Val Loss:\s*([\d.]+)"
    r".*RMSE:\s*([\d.]+).*R2:\s*(-?[\d.]+).*patience:\s*(\d+)/(\d+)"
    r".*lr:\s*([\d.e+-]+)"
)
_PRED_RE   = re.compile(r"\[val diagnostic\] pred_std=([\d.]+)")
_BEST_RE   = re.compile(r"new best")
_SHARPE_RE = re.compile(r"sharpe=([\d.e+-]+)")
_WIN_RE    = re.compile(r"win_rate=([\d.e+-]+)")

# ─── Config ───────────────────────────────────────────────────────────────────
OVERFIT_WINDOW        = 8    # epochs to measure val trend
OVERFIT_SLOPE_THRESH  = 0.002  # val_loss rising this much/epoch = overfit signal
STAGNATION_WINDOW     = 15   # epochs of no improvement before LR-reset signal
LR_RESET_COOLDOWN     = 20   # min epochs between successive LR resets
DIVERGE_THRESH        = 0.40  # val_loss > best + this -> hard diverge flag
PRINT_INTERVAL_S      = 5    # seconds between status reprints (when no new epoch)

class TrainingMonitor:
    def __init__(self, log_path: Path, signal_dir: Path, tail_from_last_run: bool = True,
                 warmup_epochs: int = 10):
        self.log_path   = log_path
        self.signal_dir = signal_dir
        self.signal_dir.mkdir(parents=True, exist_ok=True)
        self.warmup_epochs = warmup_epochs

        # Clear stale signals from previous runs
        for flag in ["lr_reset.flag", "stop_training.flag"]:
            p = signal_dir / flag
            if p.exists():
                p.unlink()
                print(DIM(f"  [monitor] Cleared stale signal: {flag}"))

        # State
        self.epochs:       list  = []   # list of dicts
        self.val_losses:   deque = deque(maxlen=OVERFIT_WINDOW)
        self.pred_stds:    list  = []
        self.best_val:     float = float("inf")
        self.best_epoch:   int   = 0
        self.last_lr_reset_epoch: int = -LR_RESET_COOLDOWN
        self.lr_reset_count: int = 0

        # Seek to start of last run if requested
        self._seek_pos = self._find_last_run_start() if tail_from_last_run else 0
        self._last_print = 0.0

    def _find_last_run_start(self) -> int:
        """Return byte offset of the last 'ENTERPRISE ST-GCN TRAINING' banner."""
        if not self.log_path.exists():
            return 0
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            idx = content.rfind("ENTERPRISE ST-GCN TRAINING")
            if idx == -1:
                return 0
            # Rewind to line start
            line_start = content.rfind("\n", 0, idx)
            return max(0, line_start)
        except Exception:
            return 0

    # ─── Signal writers ──────────────────────────────────────────────────────

    def _write_signal(self, name: str, reason: str):
        path = self.signal_dir / name
        path.write_text(reason)
        print(YELLOW(f"  [monitor]  Signal written: {name} — {reason}"))

    def _clear_signal(self, name: str):
        path = self.signal_dir / name
        if path.exists():
            path.unlink(missing_ok=True)

    # ─── Analytics ───────────────────────────────────────────────────────────

    def _linear_slope(self, values: list) -> float:
        """Least-squares slope of values (positive = increasing)."""
        n = len(values)
        if n < 2:
            return 0.0
        xs = list(range(n))
        mx = sum(xs) / n
        my = sum(values) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, values))
        den = sum((x - mx) ** 2 for x in xs)
        return num / den if den > 1e-12 else 0.0

    def _analyse(self, epoch_data: dict) -> dict:
        ep          = epoch_data["epoch"]
        train_loss  = epoch_data["train_loss"]
        val_loss    = epoch_data["val_loss"]
        patience    = epoch_data["patience"]
        max_patience = epoch_data["max_patience"]

        overfit_gap = val_loss - train_loss
        diverge_gap = val_loss - self.best_val

        # Rolling val loss slope
        vl_list = list(self.val_losses)
        val_slope = self._linear_slope(vl_list) if len(vl_list) >= 3 else 0.0

        # Decisions
        actions = []
        severity = "ok"

        # Hard guards: if loss becomes non-finite, stop immediately.
        if not (val_loss == val_loss and val_loss != float("inf") and val_loss != float("-inf")):
            actions.append("STOP")
            severity = "error"
        elif ep <= self.warmup_epochs:
            # During warmup the LR is still ramping up — val loss fluctuations are expected.
            # Never emit signals here; let the trainer finish its warmup phase.
            pass
        else:
            # 1. Overfitting (val rising while train stable/falling)
            if (len(vl_list) >= OVERFIT_WINDOW
                    and val_slope > OVERFIT_SLOPE_THRESH
                    and overfit_gap > 0.05
                    and ep - self.last_lr_reset_epoch >= LR_RESET_COOLDOWN):
                actions.append("LR_RESET")
                severity = "warn"

            # 2. Hard divergence
            #    Previously we only LR_RESET; trainer never stopped because monitor never emitted STOP.
            #    Emit STOP when we are clearly diverging beyond a stricter threshold.
            if diverge_gap > (2.0 * DIVERGE_THRESH):
                actions.append("STOP")
                severity = "error"
            elif diverge_gap > DIVERGE_THRESH and patience > max_patience // 2:
                actions.append("LR_RESET")
                severity = "error"

            # 3. Stagnation (no improvement for STAGNATION_WINDOW epochs)
            if (patience >= STAGNATION_WINDOW
                    and ep - self.last_lr_reset_epoch >= LR_RESET_COOLDOWN
                    and val_slope >= -0.0001):   # not actively improving
                actions.append("LR_RESET")
                severity = "warn"

        return {
            "overfit_gap":  overfit_gap,
            "diverge_gap":  diverge_gap,
            "val_slope":    val_slope,
            "actions":      list(set(actions)),
            "severity":     severity,
        }

    # ─── Printing ─────────────────────────────────────────────────────────────

    def _print_status(self, epoch_data: dict, analysis: dict, pred_std: Optional[float]):
        ep    = epoch_data["epoch"]
        tl    = epoch_data["train_loss"]
        vl    = epoch_data["val_loss"]
        r2    = epoch_data["r2"]
        lr    = epoch_data["lr"]
        pat   = epoch_data["patience"]
        maxp  = epoch_data["max_patience"]
        is_best = epoch_data.get("is_best", False)

        sev   = analysis["severity"]
        gap   = analysis["overfit_gap"]
        slope = analysis["val_slope"]
        dgap  = analysis["diverge_gap"]

        color = GREEN if sev == "ok" else (YELLOW if sev == "warn" else RED)
        best_tag = GREEN(" * BEST") if is_best else ""

        # Pred std bar (0.0 to 0.5 range)
        pstd_str = ""
        if pred_std is not None:
            bar_len = int(min(pred_std / 0.5, 1.0) * 20)
            bar = "#" * bar_len + "-" * (20 - bar_len)
            pstd_col = GREEN if pred_std >= 0.20 else (YELLOW if pred_std >= 0.10 else RED)
            pstd_str = f"  pred_std [{pstd_col(f'{pred_std:.3f}')}] [{bar}]"

        lines = [
            "",
            BOLD(f"  +-- Epoch {ep:03d} ------------------------------------------"),
            f"  |  Train: {tl:.4f}  │  Val: {color(f'{vl:.4f}')}  │  R²: {r2:+.4f}{best_tag}",
            f"  |  LR: {lr:.2e}  │  Patience: {pat}/{maxp}  │  Overfit gap: {gap:+.4f}",
            f"  |  Val slope ({OVERFIT_WINDOW}ep): {slope:+.5f}/ep  │  Δ from best: {dgap:+.4f}",
        ]
        if pstd_str:
            lines.append(f"  |{pstd_str}")

        if analysis["actions"]:
            for a in analysis["actions"]:
                lines.append(f"  |  " + YELLOW(f" Action queued: {a}"))

        lines.append(BOLD("  +------------------------------------------------------"))
        print("\n".join(lines))
        self._last_print = time.time()

    def _print_summary_header(self):
        recent = self.epochs[-5:] if len(self.epochs) >= 5 else self.epochs
        if not recent:
            return
        # Trend arrow
        if len(self.epochs) >= 3:
            recent_vl = [e["val_loss"] for e in self.epochs[-3:]]
            if recent_vl[-1] < recent_vl[0]:
                trend = GREEN("v improving")
            elif recent_vl[-1] > recent_vl[0] + 0.01:
                trend = RED("^ diverging")
            else:
                trend = YELLOW("-> stagnant")
        else:
            trend = DIM("...")
        
        pred_std_now = self.pred_stds[-1] if self.pred_stds else None
        pstd_display = f"{pred_std_now:.3f}" if pred_std_now else "n/a"
        
        print(
            CYAN(f"\n  [monitor] Run summary: "
                 f"best_val={self.best_val:.4f}@ep{self.best_epoch} | "
                 f"current_pred_std={pstd_display} | "
                 f"LR_resets={self.lr_reset_count} | trend={trend}")
        )

    # ─── Main loop ────────────────────────────────────────────────────────────

    def run(self, poll_interval: float = 2.0):
        print(CYAN(BOLD("\n  +---------------------------------------------------+")))
        print(CYAN(BOLD(  "  |   CryptoGraph STGCN Training Monitor  (R12)      |")))

        print(CYAN(BOLD(  "  +---------------------------------------------------+")))
        print(f"  Watching: {self.log_path}")
        print(f"  Signals -> {self.signal_dir}")
        print(f"  Overfitting detection: slope > {OVERFIT_SLOPE_THRESH}/ep over {OVERFIT_WINDOW} epochs")
        print(f"  LR reset cooldown: {LR_RESET_COOLDOWN} epochs\n")

        pending_pred_std: Optional[float] = None

        with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(self._seek_pos)
            buffer = ""

            while True:
                chunk = f.read(4096)
                if chunk:
                    buffer += chunk
                    lines = buffer.split("\n")
                    buffer = lines[-1]   # incomplete line

                    for line in lines[:-1]:
                        # Pred std
                        m = _PRED_RE.search(line)
                        if m:
                            pending_pred_std = float(m.group(1))
                            self.pred_stds.append(pending_pred_std)

                        # Epoch line
                        m = _EPOCH_RE.search(line)
                        if m:
                            ep, tl, vl, rmse, r2, pat, maxp, lr = (
                                int(m.group(1)),
                                float(m.group(2)),
                                float(m.group(3)),
                                float(m.group(4)),
                                float(m.group(5)),
                                int(m.group(6)),
                                int(m.group(7)),
                                float(m.group(8)),
                            )
                            is_best = bool(_BEST_RE.search(line))

                            if vl < self.best_val:
                                self.best_val   = vl
                                self.best_epoch = ep

                            epoch_data = {
                                "epoch": ep, "train_loss": tl, "val_loss": vl,
                                "rmse": rmse, "r2": r2, "patience": pat,
                                "max_patience": maxp, "lr": lr, "is_best": is_best,
                            }
                            self.epochs.append(epoch_data)
                            self.val_losses.append(vl)

                            analysis = self._analyse(epoch_data)
                            self._print_status(epoch_data, analysis, pending_pred_std)
                            pending_pred_std = None

                            # Execute actions
                            if "LR_RESET" in analysis["actions"]:
                                self._write_signal(
                                    "lr_reset.flag",
                                    f"epoch={ep} val_slope={analysis['val_slope']:+.5f} "
                                    f"overfit_gap={analysis['overfit_gap']:+.4f}"
                                )
                                self.last_lr_reset_epoch = ep
                                self.lr_reset_count += 1

                            if "STOP" in analysis["actions"]:
                                self._write_signal("stop_training.flag",
                                                   f"epoch={ep} diverge_gap={analysis['diverge_gap']:.4f}")

                            if ep % 20 == 0:
                                self._print_summary_header()

                else:
                    # No new data — print keepalive if TTY
                    if time.time() - self._last_print > PRINT_INTERVAL_S and sys.stdout.isatty():
                        print(DIM(f"  [monitor] waiting... best={self.best_val:.4f}@ep{self.best_epoch}"),
                              end="\r", flush=True)
                    time.sleep(poll_interval)


def main():
    parser = argparse.ArgumentParser(description="CryptoGraph Training Monitor")
    parser.add_argument("--log",        type=Path, default=_DEFAULT_LOG,
                        help="Path to logs.txt")
    parser.add_argument("--signal-dir", type=Path, default=_DEFAULT_SIGNAL_DIR,
                        help="Directory to write signal files")
    parser.add_argument("--from-start", action="store_true",
                        help="Tail from beginning of file instead of last run")
    parser.add_argument("--poll",       type=float, default=2.0,
                        help="Poll interval in seconds")
    args = parser.parse_args()

    monitor = TrainingMonitor(
        log_path=args.log,
        signal_dir=args.signal_dir,
        tail_from_last_run=not args.from_start,
    )
    try:
        monitor.run(poll_interval=args.poll)
    except KeyboardInterrupt:
        print(CYAN("\n  [monitor] Stopped by user."))


if __name__ == "__main__":
    main()
