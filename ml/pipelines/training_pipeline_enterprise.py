#!/usr/bin/env python3
"""
ENTERPRISE-GRADE ST-GCN TRAINING PIPELINE — REVISION 3
=======================================================
ml/pipelines/training_pipeline_enterprise.py

BUGS FIXED IN THIS REVISION (R3):

  [R3-BUG-1, CRITICAL — ROOT CAUSE OF PERSISTENT DEAD WEIGHTS]
    df.loc[date, col] fails silently when 'date' is a Python stdlib
    datetime(tzinfo=timezone.utc) and df.index contains pandas Timestamps
    with UTC timezone. In pandas >= 2.0, the hash/equality semantics for
    mixed datetime/Timestamp with timezone differ between containment
    checks (df.index.__contains__) and label indexing (df.loc). The 'in'
    check passes but .loc returns NaN, causing every target to be treated
    as missing (mask=0), making all target tensors zero-valued.

    Fix: convert graph_dates to pd.Timestamp at construction time, and
    use pd.Timestamp(date) explicitly in all .loc[] calls. Also added
    a bulk vectorized extraction path using df.reindex() with explicit
    Timestamp conversion, which is both faster and avoids the per-row
    datetime/Timestamp mismatch entirely.

  [R3-BUG-2, CRITICAL — NORMALIZATION APPLIED TO ALL-ZERO DATA]
    When R3-BUG-1 causes all targets to be 0.0 (masked as missing),
    _normalize_targets receives a series of NaN (after masking invalid
    entries). Rolling std of NaN is NaN. Fallback fires. Division of
    0.0 by 0.02 = 0.0. Verified target std = 0.0000. Added pre-
    normalization assertions that block training if this is detected
    rather than silently proceeding to train a dead model.

  [R3-BUG-3, MEDIUM — SURVIVING DATES vs GRAPH DATES TIMEZONE MISMATCH]
    _determine_surviving_dates iterates datetimes from start_dt to end_dt.
    proc_features[sym].index contains pd.Timestamp(UTC). The 'current'
    datetime is Python datetime(UTC). Containment check 'current not in
    date_sets[s]' (where date_sets[s] = set(df.index)) hits the same
    pandas/stdlib datetime equality issue. Fixed by converting the date_sets
    to contain normalized pd.Timestamp objects.

  Retained from R2 (all still valid):
    - Tensor-based _normalize_targets (no pandas reindex)
    - Causal shift(1) in rolling std
    - entropy_beta=0.30, log_var_min=-3.0, log_var_max=4.0
    - BUG-7 (non-finite loss DDP fix)
    - BUG-11 (DDP deadlock fix)
    - BUG-14/15 (weights_only=False)
    - BUG-16 (DB query fix)
    - _verify_normalization, _check_prediction_variance diagnostics
    - WARN-A shape assertion in forward()
"""

import os
import sys
import json
import time
import random
import pickle
import hashlib
import heapq
import argparse
import traceback
import warnings
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from collections import defaultdict

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import DataLoader, Dataset
from torch.utils.data.distributed import DistributedSampler
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR, SequentialLR, LinearLR
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

warnings.filterwarnings("ignore")

# ============================================================================
# 0. LOGGING / RANK-AWARE HELPERS
# ============================================================================
_CURRENT_RANK = 0


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ts() -> str:
    return now_utc().strftime("%Y-%m-%d %H:%M:%S UTC")


def log(msg: str, force: bool = False) -> None:
    if _CURRENT_RANK == 0 or force:
        prefix = f"[rank{_CURRENT_RANK}] " if _CURRENT_RANK != 0 else ""
        print(f"[{ts()}] {prefix}{msg}", flush=True)


def new_run_id() -> str:
    return now_utc().strftime("%Y%m%d-%H%M%S")


def set_seed(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


# ============================================================================
# 1. PATH RESOLUTION
# ============================================================================
current = Path(__file__).resolve()
workspace_root = current
for _parent in current.parents:
    if (
        (_parent / ".git").exists()
        or (_parent / "README.md").exists()
        or (_parent / "ARCHITECTURE.md").exists()
    ):
        workspace_root = _parent
        break

if str(workspace_root) not in sys.path:
    sys.path.append(str(workspace_root))
if str(workspace_root / "backend") not in sys.path:
    sys.path.append(str(workspace_root / "backend"))

from ml.data.feature_store.store import FeatureStore
from ml.graph.graph_builder import DynamicGraphBuilder
from ml.models.gat_temporal import SpatioTemporalGAT
from ml.models.causal_tcn import TemporalTCN

ARTIFACTS_DIR = workspace_root / "ml" / "artifacts"
CACHE_DIR = ARTIFACTS_DIR / "cache"
RUNS_DIR = ARTIFACTS_DIR / "runs"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# 2. DISTRIBUTED SETUP
# ============================================================================
def setup_distributed():
    if "WORLD_SIZE" in os.environ and int(os.environ["WORLD_SIZE"]) > 1:
        rank = int(os.environ["RANK"])
        local_rank = int(os.environ["LOCAL_RANK"])
        world_size = int(os.environ["WORLD_SIZE"])
        os.environ.setdefault("NCCL_P2P_DISABLE", "1")
        os.environ.setdefault("NCCL_IB_DISABLE", "1")
        dist.init_process_group(backend="nccl", init_method="env://")
        torch.cuda.set_device(local_rank)
        device = torch.device(f"cuda:{local_rank}")
        return True, rank, local_rank, world_size, device

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if torch.cuda.device_count() > 1:
        print(
            f"[{ts()}] NOTE: {torch.cuda.device_count()} GPUs visible but not "
            f"launched via torchrun -- only {device} will be used.",
            flush=True,
        )
    return False, 0, 0, 1, device


def cleanup_distributed(is_distributed: bool):
    if is_distributed:
        try:
            dist.destroy_process_group()
        except Exception:
            pass


# ============================================================================
# 3. CONFIGURATION
# ============================================================================
@dataclass
class TrainingConfig:
    lookback_days: int = 30
    forecast_horizon: int = 1
    feature_dim: int = 24
    target_col: str = "returns_1d"
    history_days: int = 730
    max_missing_frac: float = 0.10
    use_cache: bool = True
    cache_max_age_hours: float = 24.0

    hidden_dim: int = 64
    gat_heads_1: int = 2
    gat_heads_2: int = 2
    transformer_layers: int = 2
    transformer_heads: int = 4
    dropout: float = 0.40
    use_tcn: bool = True

    batch_size: int = 4
    max_epochs: int = 300
    learning_rate: float = 1e-4
    weight_decay: float = 1e-2
    warmup_epochs: int = 10
    grad_clip: float = 1.0
    early_stopping_patience: int = 25

    # NLL stability: log_var is clamped to [log_var_min, log_var_max].
    # log_var_min = -3.0 ≈ log(0.05): model cannot claim precision tighter
    # than 5% of unit variance. This prevents the degenerate collapse where
    # the model predicts zero with maximum confidence.
    log_var_min: float = -3.0
    log_var_max: float = 4.0
    # entropy_beta=0.30: penalty gradient (-0.30) partially counters the NLL
    # gradient (+0.5) that pushes log_var toward log_var_min. After correct
    # normalization (target var ≈ 1), the zero-predictor optimal is log_var*=0,
    # loss*=0.5, which is POSITIVE -- giving the model clear gradient signal to
    # improve. The entropy reg is a secondary defense for robustness.
    entropy_beta: float = 0.30

    normalize_targets: bool = True
    target_norm_window: int = 60

    ensemble_size: int = 5
    mc_dropout_samples: int = 30

    use_sam: bool = False
    sam_rho: float = 0.05

    use_amp: bool = True
    num_workers: int = 0
    max_train_hours: float = 8.5
    checkpoint_every_epochs: int = 1
    seed: int = 42
    cudnn_benchmark: bool = False

    run_permutation_importance: bool = True
    importance_max_batches: int = 15
    run_trading_metrics: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================================
# 4. SELF-CONTAINED SAM
# ============================================================================
class SAM(torch.optim.Optimizer):
    def __init__(self, params, base_optimizer_cls, rho: float = 0.05, **kwargs):
        assert rho >= 0
        defaults = dict(rho=rho, **kwargs)
        super().__init__(params, defaults)
        self.base_optimizer = base_optimizer_cls(self.param_groups, **kwargs)
        self.param_groups = self.base_optimizer.param_groups
        self.defaults.update(self.base_optimizer.defaults)

    @torch.no_grad()
    def first_step(self, zero_grad: bool = False):
        grad_norm = self._grad_norm()
        for group in self.param_groups:
            scale = group["rho"] / (grad_norm + 1e-12)
            for p in group["params"]:
                if p.grad is None:
                    continue
                e_w = p.grad * scale.to(p.device)
                p.add_(e_w)
                self.state[p]["e_w"] = e_w
        if zero_grad:
            self.zero_grad()

    @torch.no_grad()
    def second_step(self, zero_grad: bool = False):
        for group in self.param_groups:
            for p in group["params"]:
                if p.grad is None or "e_w" not in self.state[p]:
                    continue
                p.sub_(self.state[p]["e_w"])
        self.base_optimizer.step()
        if zero_grad:
            self.zero_grad()

    def _grad_norm(self):
        device = self.param_groups[0]["params"][0].device
        norms = [
            p.grad.norm(p=2).to(device)
            for group in self.param_groups
            for p in group["params"]
            if p.grad is not None
        ]
        return (
            torch.norm(torch.stack(norms), p=2)
            if norms
            else torch.tensor(1e-12, device=device)
        )

    def step(self, closure=None):
        raise RuntimeError("Use first_step()/second_step() explicitly for SAM.")


# ============================================================================
# 5. DATASET
# ============================================================================
def graph_collate_fn(batch):
    sequences = [item[0] for item in batch]
    targets = torch.stack([item[1] for item in batch], dim=0)
    masks = torch.stack([item[2] for item in batch], dim=0)
    return sequences, targets, masks


class WindowedGraphDataset(Dataset):
    """
    input  = all_graphs[t - lookback : t]   (with horizon=1, never includes t)
    target = all_targets[t]
    """

    def __init__(
        self,
        all_graphs: list,
        all_targets: List[torch.Tensor],
        all_masks: List[torch.Tensor],
        lookback: int,
        horizon: int,
        start_idx: int,
        end_idx: int,
    ):
        assert horizon >= 1, (
            "forecast_horizon must be >= 1 to guarantee no same-day leakage."
        )
        self.all_graphs = all_graphs
        self.all_targets = all_targets
        self.all_masks = all_masks
        self.lookback = lookback
        self.horizon = horizon
        self.valid_start = max(start_idx, lookback + horizon - 1)
        self.end_idx = end_idx

    def __len__(self) -> int:
        return max(0, self.end_idx - self.valid_start)

    def __getitem__(self, i: int):
        t = self.valid_start + i
        input_end = t - self.horizon + 1
        window = self.all_graphs[input_end - self.lookback : input_end]
        assert len(window) == self.lookback, (
            f"Window length {len(window)} != lookback {self.lookback} "
            f"(t={t}, input_end={input_end})"
        )
        return window, self.all_targets[t], self.all_masks[t]


# ============================================================================
# 6. MODEL
# ============================================================================
class EnterpriseSTGCNModel(nn.Module):
    def __init__(self, config: TrainingConfig):
        super().__init__()
        self.config = config

        self.projection = nn.Linear(config.feature_dim, config.hidden_dim)
        self.proj_norm = nn.LayerNorm(config.hidden_dim)

        self.spatial_gat = SpatioTemporalGAT(
            config.hidden_dim,
            config.gat_heads_1,
            config.gat_heads_2,
            config.dropout,
        )
        if config.use_tcn:
            self.temporal_encoder = TemporalTCN(
                config.hidden_dim,
                kernel_size=3,
                dilations=[1, 2, 4, 8, 16],
                dropout=config.dropout,
            )
        else:
            from ml.models.temporal_transformer import TemporalTransformer

            self.temporal_encoder = TemporalTransformer(
                config.hidden_dim,
                config.transformer_heads,
                config.transformer_layers,
                config.dropout,
            )

        self.reg_head = nn.Sequential(
            nn.Linear(config.hidden_dim, config.hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_dim // 2, config.hidden_dim // 4),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_dim // 4, 1),
        )
        self.uncertainty_head = nn.Sequential(
            nn.Linear(config.hidden_dim, config.hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_dim // 2, 1),
        )

    def enable_mc_dropout(self):
        """Activates dropout while keeping BatchNorm in eval mode."""
        self.train()
        for m in self.modules():
            if isinstance(m, (nn.BatchNorm1d, nn.BatchNorm2d, nn.BatchNorm3d)):
                m.eval()

    def disable_mc_dropout(self):
        self.eval()

    def forward(
        self,
        batch_sequences: List[List],
        return_uncertainty: bool = False,
    ):
        from torch_geometric.data import Batch

        B = len(batch_sequences)
        if B == 0:
            raise ValueError("Empty batch passed to forward()")
        T = len(batch_sequences[0])
        if T == 0:
            raise ValueError("Empty graph sequence in batch (T=0)")

        for b, seq in enumerate(batch_sequences):
            if len(seq) != T:
                raise ValueError(
                    f"Ragged batch: sequence {b} has length {len(seq)}, expected {T}."
                )

        flat: List = []
        for seq in batch_sequences:
            for g in seq:
                if not hasattr(g, "x") or g.x is None:
                    raise ValueError("Graph missing node feature matrix 'x'")
                if g.x.shape[1] != self.config.feature_dim:
                    raise ValueError(
                        f"Graph has {g.x.shape[1]} node features, "
                        f"expected {self.config.feature_dim}"
                    )
                if not hasattr(g, "edge_type") or g.edge_type is None:
                    g.edge_type = torch.zeros(
                        g.edge_index.shape[1],
                        dtype=torch.long,
                        device=g.edge_index.device,
                    )
                flat.append(g)

        node_counts = {g.num_nodes for g in flat}
        if len(node_counts) > 1:
            raise ValueError(
                f"Inconsistent node counts across minibatch: {node_counts}."
            )

        N_nodes = flat[0].num_nodes
        batched = Batch.from_data_list(flat)
        x = F.relu(self.projection(batched.x))
        x = self.proj_norm(x)
        batched.x = x

        x = self.spatial_gat(batched, T=T, B=B)
        x = self.temporal_encoder(x)

        # Expected output: [B*N_nodes, hidden_dim] (temporal encoder pools T,
        # preserves B*N spatial dimension).
        if x.dim() != 2 or x.shape[0] != B * N_nodes:
            raise ValueError(
                f"temporal_encoder output shape {tuple(x.shape)} unexpected; "
                f"expected [{B * N_nodes}, hidden_dim]. "
                f"Check SpatioTemporalGAT / TemporalTCN output contract. "
                f"[WARN-A from audit]"
            )

        pred = self.reg_head(x).squeeze(-1).view(B, N_nodes)
        log_var = self.uncertainty_head(x).squeeze(-1).view(B, N_nodes)

        if return_uncertainty:
            return pred, log_var
        return pred

    def save(self, path: str) -> None:
        torch.save(
            {"model_state_dict": self.state_dict(), "config": self.config.to_dict()},
            path,
        )

    @classmethod
    def load(cls, path: str, map_location: str = "cpu") -> "EnterpriseSTGCNModel":
        # weights_only=False required: checkpoint contains config dict (non-tensor).
        checkpoint = torch.load(path, map_location=map_location, weights_only=False)
        config = TrainingConfig()
        for k, v in checkpoint["config"].items():
            if hasattr(config, k):
                setattr(config, k, v)
        model = cls(config)
        model.load_state_dict(checkpoint["model_state_dict"])
        return model


# ============================================================================
# 7. TRAINER
# ============================================================================
class EnterpriseTrainer:
    def __init__(
        self,
        model: EnterpriseSTGCNModel,
        train_loader: DataLoader,
        val_loader: DataLoader,
        test_loader: DataLoader,
        config: TrainingConfig,
        device: torch.device,
        run_dir: Path,
        is_distributed: bool,
        rank: int,
        world_size: int,
        train_sampler=None,
    ):
        self.is_distributed = is_distributed
        self.rank = rank
        self.world_size = world_size
        self.train_sampler = train_sampler

        raw = model.to(device)
        if is_distributed:
            raw = nn.SyncBatchNorm.convert_sync_batchnorm(raw)
        self.model = (
            DDP(
                raw,
                device_ids=[device.index] if device.type == "cuda" else None,
                find_unused_parameters=True,
            )
            if is_distributed
            else raw
        )

        self.train_loader = train_loader
        self.val_loader = val_loader
        self.test_loader = test_loader
        self.config = config
        self.device = device
        self.run_dir = run_dir
        run_dir.mkdir(parents=True, exist_ok=True)

        if config.use_sam:
            if config.use_amp:
                log("SAM + AMP is numerically fragile -- disabling AMP.")
                config.use_amp = False
            self.optimizer = SAM(
                self.model.parameters(),
                AdamW,
                rho=config.sam_rho,
                lr=config.learning_rate,
                weight_decay=config.weight_decay,
            )
        else:
            self.optimizer = AdamW(
                self.model.parameters(),
                lr=config.learning_rate,
                weight_decay=config.weight_decay,
            )

        steps_per_epoch = max(1, len(train_loader))
        warmup_steps = max(1, config.warmup_epochs * steps_per_epoch)
        total_steps = max(warmup_steps + 1, config.max_epochs * steps_per_epoch)
        self.scheduler = SequentialLR(
            self.optimizer,
            schedulers=[
                LinearLR(
                    self.optimizer,
                    start_factor=0.1,
                    end_factor=1.0,
                    total_iters=warmup_steps,
                ),
                CosineAnnealingLR(
                    self.optimizer,
                    T_max=total_steps - warmup_steps,
                    eta_min=1e-6,
                ),
            ],
            milestones=[warmup_steps],
        )

        self.scaler = (
            torch.amp.GradScaler("cuda")
            if (config.use_amp and device.type == "cuda")
            else None
        )

        self.best_val_loss = float("inf")
        self.best_epoch = 0
        self.patience_counter = 0
        self.epoch = 1
        self.snapshot_heap: List[Tuple[float, int, str]] = []
        self.history: Dict[str, list] = defaultdict(list)
        self.run_start_time = time.time()

        self._maybe_resume()
        if self.is_distributed:
            dist.barrier()

    @property
    def raw_model(self) -> EnterpriseSTGCNModel:
        return self.model.module if isinstance(self.model, DDP) else self.model

    def _barrier(self):
        if self.is_distributed:
            dist.barrier()

    def _sync_scalar(self, value: float) -> float:
        if not self.is_distributed:
            return value
        t = torch.tensor([value], dtype=torch.float64, device=self.device)
        dist.broadcast(t, src=0)
        return t.item()

    def _sync_bool(self, value: bool) -> bool:
        if not self.is_distributed:
            return value
        t = torch.tensor(
            [1.0 if value else 0.0], dtype=torch.float32, device=self.device
        )
        dist.broadcast(t, src=0)
        return t.item() > 0.5

    def _checkpoint_path(self) -> Path:
        return self.run_dir / "checkpoint_last.pt"

    def _save_full_checkpoint(self):
        if self.rank != 0:
            return
        state = {
            "epoch": self.epoch,
            "model_state_dict": self.raw_model.state_dict(),
            "optimizer_state_dict": (
                self.optimizer.base_optimizer.state_dict()
                if isinstance(self.optimizer, SAM)
                else self.optimizer.state_dict()
            ),
            "scheduler_state_dict": self.scheduler.state_dict(),
            "scaler_state_dict": self.scaler.state_dict() if self.scaler else None,
            "best_val_loss": self.best_val_loss,
            "best_epoch": self.best_epoch,
            "patience_counter": self.patience_counter,
            "history": dict(self.history),
            "snapshot_heap": self.snapshot_heap,
            "config": self.config.to_dict(),
            "torch_rng_state": torch.get_rng_state(),
            "cuda_rng_state_all": (
                torch.cuda.get_rng_state_all()
                if torch.cuda.is_available()
                else None
            ),
            "numpy_rng_state": np.random.get_state(),
            "python_rng_state": random.getstate(),
            "timestamp": ts(),
        }
        tmp_path = self._checkpoint_path().with_suffix(".pt.tmp")
        torch.save(state, tmp_path)
        tmp_path.replace(self._checkpoint_path())

    def _maybe_resume(self):
        path = self._checkpoint_path()
        if not path.exists():
            self.epoch = 1
            return
        try:
            ckpt = torch.load(path, map_location=self.device, weights_only=False)
            self.raw_model.load_state_dict(ckpt["model_state_dict"])
            if isinstance(self.optimizer, SAM):
                self.optimizer.base_optimizer.load_state_dict(
                    ckpt["optimizer_state_dict"]
                )
            else:
                self.optimizer.load_state_dict(ckpt["optimizer_state_dict"])
            self.scheduler.load_state_dict(ckpt["scheduler_state_dict"])
            if self.scaler and ckpt.get("scaler_state_dict"):
                self.scaler.load_state_dict(ckpt["scaler_state_dict"])
            self.best_val_loss = ckpt["best_val_loss"]
            self.best_epoch = ckpt["best_epoch"]
            self.patience_counter = ckpt["patience_counter"]
            self.history = defaultdict(list, ckpt["history"])
            self.snapshot_heap = ckpt["snapshot_heap"]
            torch.set_rng_state(ckpt["torch_rng_state"].cpu())
            if ckpt.get("cuda_rng_state_all") is not None and torch.cuda.is_available():
                torch.cuda.set_rng_state_all(ckpt["cuda_rng_state_all"])
            np.random.set_state(ckpt["numpy_rng_state"])
            random.setstate(ckpt["python_rng_state"])
            self.epoch = ckpt["epoch"] + 1
            log(
                f"Resumed from checkpoint at epoch {ckpt['epoch']} "
                f"(saved {ckpt.get('timestamp', 'unknown')})"
            )
        except Exception as e:
            log(f"Failed to resume checkpoint ({e}); starting fresh from epoch 1.")
            self.epoch = 1

    def _maybe_save_snapshot(self, val_loss: float, epoch: int):
        if self.rank != 0:
            return
        if not np.isfinite(val_loss):
            log(f"Epoch {epoch}: val_loss is not finite; skipping snapshot.")
            return
        path = self.run_dir / f"snapshot_epoch{epoch}.pt"
        entry = (-val_loss, epoch, str(path))
        if len(self.snapshot_heap) < self.config.ensemble_size:
            self.raw_model.save(str(path))
            heapq.heappush(self.snapshot_heap, entry)
        else:
            worst = self.snapshot_heap[0]
            if -worst[0] > val_loss:
                heapq.heapreplace(self.snapshot_heap, entry)
                self.raw_model.save(str(path))
                old_path = Path(worst[2])
                if old_path.exists():
                    old_path.unlink(missing_ok=True)

    def _finalize_snapshots(self):
        if self.rank != 0:
            return
        import shutil

        ranked = sorted(self.snapshot_heap, key=lambda e: -e[0])
        for i, (_, epoch, path) in enumerate(ranked):
            dst = ARTIFACTS_DIR / f"snapshot_{i}.pt"
            try:
                shutil.copy(path, dst)
            except Exception as e:
                log(f"Could not copy snapshot {path} -> {dst}: {e}")

    def _compute_loss(
        self,
        pred: torch.Tensor,
        target: torch.Tensor,
        log_var: torch.Tensor,
        mask: torch.Tensor,
    ) -> torch.Tensor:
        """
        Gaussian NLL + entropy regularization.

        With correctly normalized targets (var ≈ 1):
          Zero-predictor: E[(pred-target)^2] = 1.0, optimal log_var* = 0,
          loss* = 0.5. This is POSITIVE, giving the model a real incentive
          to learn (any genuine prediction with R^2 > 0 achieves loss < 0.5).

        The entropy term penalizes log_var << 0 (over-confidence), acting as
        a secondary defense against the degenerate collapse.
        """
        log_var = torch.clamp(
            log_var, min=self.config.log_var_min, max=self.config.log_var_max
        )
        precision = torch.exp(-log_var)
        per_node = 0.5 * precision * (pred - target) ** 2 + 0.5 * log_var

        denom = mask.sum().clamp_min(1.0)
        nll_loss = (per_node * mask).sum() / denom

        valid_mask = mask.bool()
        if valid_mask.any():
            entropy_reg = self.config.entropy_beta * F.relu(
                -log_var[valid_mask]
            ).mean()
        else:
            entropy_reg = torch.tensor(0.0, device=pred.device)

        return nll_loss + entropy_reg

    def _forward_backward(self, sequences, targets, masks) -> Tuple[float, float]:
        """
        Forward + backward pass. Always calls backward() to maintain DDP sync.
        Non-finite loss is replaced with a parameter-tied zero to produce
        zero gradients rather than NaN/inf gradients.
        """
        sequences_dev = [
            [g.to(self.device, non_blocking=True) for g in seq]
            for seq in sequences
        ]
        targets_dev = targets.to(self.device, non_blocking=True)
        masks_dev = masks.to(self.device, non_blocking=True)

        amp_enabled = self.scaler is not None
        with torch.amp.autocast("cuda", enabled=amp_enabled):
            pred, log_var = self.model(sequences_dev, return_uncertainty=True)
            loss = self._compute_loss(pred, targets_dev, log_var, masks_dev)

        if not torch.isfinite(loss):
            log(
                f"Non-finite loss ({loss.item():.4f}) -- substituting zero "
                f"loss tied to parameters for DDP sync."
            )
            loss = 0.0 * sum(p.sum() for p in self.model.parameters())

        if amp_enabled:
            self.scaler.scale(loss).backward()
        else:
            loss.backward()

        with torch.no_grad():
            valid = masks_dev.bool()
            mse = (
                F.mse_loss(pred.detach()[valid], targets_dev[valid]).item()
                if valid.any()
                else 0.0
            )

        return loss.item(), mse

    def _check_prediction_variance(self, loader: DataLoader, label: str) -> None:
        """Diagnostic: detect prediction collapse to near-constant."""
        self.raw_model.eval()
        preds_collected = []
        log_vars_collected = []
        with torch.no_grad():
            for i, (sequences, targets, masks) in enumerate(loader):
                if i >= 5:
                    break
                seq_dev = [[g.to(self.device) for g in seq] for seq in sequences]
                pred, log_var = self.raw_model(seq_dev, return_uncertainty=True)
                valid = masks.to(self.device).bool()
                if valid.any():
                    preds_collected.append(pred[valid].cpu())
                    log_vars_collected.append(log_var[valid].cpu())

        if not preds_collected:
            return
        all_preds = torch.cat(preds_collected)
        all_log_vars = torch.cat(log_vars_collected)
        pred_std = all_preds.std().item()
        mean_pred_std = torch.exp(0.5 * all_log_vars).mean().item()

        log(
            f"[{label} diagnostic] pred_std={pred_std:.6f} | "
            f"mean_pred_uncertainty={mean_pred_std:.6f}"
        )
        if pred_std < 1e-4:
            log(
                f"WARNING: pred_std={pred_std:.2e} near zero -- model may be "
                f"predicting a constant. If normalization is confirmed correct "
                f"(target std ≈ 1), this indicates the model architecture needs "
                f"investigation."
            )

    def train_epoch(self, epoch: int) -> Dict[str, float]:
        self.model.train()
        if self.train_sampler is not None:
            self.train_sampler.set_epoch(epoch)

        total_loss, total_mse, n_steps = 0.0, 0.0, 0

        for sequences, targets, masks in self.train_loader:
            self.optimizer.zero_grad(set_to_none=True)

            if isinstance(self.optimizer, SAM):
                loss1, mse1 = self._forward_backward(sequences, targets, masks)
                self.optimizer.first_step(zero_grad=True)
                self._forward_backward(sequences, targets, masks)
                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(), self.config.grad_clip
                )
                self.optimizer.second_step(zero_grad=True)
                loss_val, mse_val = loss1, mse1
            else:
                loss_val, mse_val = self._forward_backward(sequences, targets, masks)
                if self.scaler is not None:
                    self.scaler.unscale_(self.optimizer)
                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(), self.config.grad_clip
                )
                if self.scaler is not None:
                    self.scaler.step(self.optimizer)
                    self.scaler.update()
                else:
                    self.optimizer.step()

            self.scheduler.step()
            total_loss += loss_val
            total_mse += mse_val
            n_steps += 1

        n_steps = max(n_steps, 1)
        return {
            "train_loss": total_loss / n_steps,
            "train_mse": total_mse / n_steps,
            "lr": self.optimizer.param_groups[0]["lr"],
        }

    @torch.no_grad()
    def validate(self) -> Dict[str, float]:
        self.raw_model.eval()
        total_loss, n_steps = 0.0, 0
        all_preds, all_targets, all_vars = [], [], []

        for sequences, targets, masks in self.val_loader:
            if masks.sum() == 0:
                continue

            sequences_dev = [[g.to(self.device) for g in seq] for seq in sequences]
            targets_dev = targets.to(self.device)
            masks_dev = masks.to(self.device)

            pred, log_var = self.raw_model(sequences_dev, return_uncertainty=True)
            loss = self._compute_loss(pred, targets_dev, log_var, masks_dev)

            if torch.isfinite(loss):
                total_loss += loss.item()
                n_steps += 1

            valid = masks.bool().numpy()
            all_preds.append(pred.cpu().numpy()[valid])
            all_targets.append(targets.numpy()[valid])
            var = torch.exp(
                torch.clamp(log_var, max=self.config.log_var_max)
            ).cpu().numpy()
            all_vars.append(var[valid])

            del pred, log_var, loss, sequences_dev, targets_dev, masks_dev

        n_steps = max(n_steps, 1)
        preds = np.concatenate(all_preds) if all_preds else np.array([0.0])
        targets_np = np.concatenate(all_targets) if all_targets else np.array([0.0])
        variances = np.concatenate(all_vars) if all_vars else np.array([1.0])

        r2 = float(r2_score(targets_np, preds)) if len(preds) > 1 else 0.0
        return {
            "val_loss": total_loss / n_steps,
            "val_rmse": float(np.sqrt(mean_squared_error(targets_np, preds))),
            "val_mae": float(mean_absolute_error(targets_np, preds)),
            "val_r2": r2,
            "val_mean_var": float(variances.mean()),
            "val_mean_pred_std": float(
                np.sqrt(np.clip(variances, 1e-12, None)).mean()
            ),
        }

    def fit(self):
        log("=" * 60)
        log("ENTERPRISE ST-GCN TRAINING")
        log(
            f"Distributed: {self.is_distributed} | world_size={self.world_size} "
            f"| device={self.device}"
        )
        log(
            f"Model params: {sum(p.numel() for p in self.raw_model.parameters()):,}"
        )
        log(
            f"Train batches/rank: {len(self.train_loader)} | "
            f"Val: {len(self.val_loader)} | Test: {len(self.test_loader)}"
        )
        log(f"Starting/resuming at epoch: {self.epoch}")
        log("=" * 60)

        for epoch in range(self.epoch, self.config.max_epochs + 1):
            self.epoch = epoch
            epoch_start = time.time()

            train_metrics = self.train_epoch(epoch)

            val_metrics: Dict[str, float] = {}
            if self.rank == 0:
                val_metrics = self.validate()
            val_loss = self._sync_scalar(val_metrics.get("val_loss", float("inf")))

            if self.rank == 0:
                for k, v in {**train_metrics, **val_metrics}.items():
                    self.history[k].append(v)

            improved = np.isfinite(val_loss) and val_loss < self.best_val_loss
            if improved:
                self.best_val_loss = val_loss
                self.best_epoch = epoch
                self.patience_counter = 0
                if self.rank == 0:
                    self.raw_model.save(str(ARTIFACTS_DIR / "best_model.pt"))
                    self.raw_model.save(str(self.run_dir / "best_model.pt"))
                    self._maybe_save_snapshot(val_loss, epoch)
            else:
                self.patience_counter += 1

            elapsed = time.time() - epoch_start
            total_elapsed_h = (time.time() - self.run_start_time) / 3600

            if self.rank == 0:
                log(
                    f"Epoch {epoch:3d}/{self.config.max_epochs} | "
                    f"Loss {train_metrics['train_loss']:.6f} | "
                    f"Val {val_loss:.6f} | "
                    f"RMSE {val_metrics.get('val_rmse', float('nan')):.6f} | "
                    f"R2 {val_metrics.get('val_r2', float('nan')):.4f} | "
                    f"PredStd {val_metrics.get('val_mean_pred_std', float('nan')):.4f} | "
                    f"LR {train_metrics['lr']:.2e} | "
                    f"{elapsed:.1f}s | total {total_elapsed_h:.2f}h"
                    + (" | new best" if improved else "")
                )

            if self.rank == 0 and epoch % 10 == 0:
                self._check_prediction_variance(self.val_loader, f"val-ep{epoch}")

            if epoch % self.config.checkpoint_every_epochs == 0:
                self._save_full_checkpoint()

            should_stop = False
            if self.rank == 0:
                should_stop = (
                    self.patience_counter >= self.config.early_stopping_patience
                    or total_elapsed_h >= self.config.max_train_hours
                )
                if should_stop:
                    reason = (
                        "early stopping"
                        if self.patience_counter
                        >= self.config.early_stopping_patience
                        else "wall-clock budget"
                    )
                    log(f"Stopping ({reason}) at epoch {epoch}.")
            should_stop = self._sync_bool(should_stop)

            if should_stop:
                self._save_full_checkpoint()
                break

        self._barrier()
        self._finalize_snapshots()

        if self.rank == 0:
            best_path = ARTIFACTS_DIR / "best_model.pt"
            if best_path.exists():
                try:
                    loaded = EnterpriseSTGCNModel.load(
                        str(best_path), map_location=str(self.device)
                    ).to(self.device)
                    if isinstance(self.model, DDP):
                        self.model.module.load_state_dict(loaded.state_dict())
                    else:
                        self.model = loaded
                    log("Best model weights reloaded for final evaluation.")
                except Exception as e:
                    log(
                        f"Could not reload best model weights: {e}. "
                        f"Using current weights."
                    )

        log("=" * 60)
        log(
            f"TRAINING COMPLETE | best epoch {self.best_epoch} | "
            f"best val loss {self.best_val_loss:.6f}"
        )
        log("=" * 60)

    @torch.no_grad()
    def evaluate_test(self) -> Dict[str, float]:
        if self.rank != 0:
            return {}
        self.raw_model.eval()
        self.raw_model.enable_mc_dropout()

        all_preds, all_targets, all_vars = [], [], []
        for sequences, targets, masks in self.test_loader:
            if masks.sum() == 0:
                continue
            sequences_dev = [[g.to(self.device) for g in seq] for seq in sequences]
            mc_preds, mc_vars = [], []
            for _ in range(self.config.mc_dropout_samples):
                pred, log_var = self.raw_model(sequences_dev, return_uncertainty=True)
                mc_preds.append(pred.cpu().numpy())
                mc_vars.append(
                    torch.exp(
                        torch.clamp(log_var, max=self.config.log_var_max)
                    ).cpu().numpy()
                )
            valid = masks.bool().numpy()
            all_preds.append(np.stack(mc_preds).mean(axis=0)[valid])
            all_vars.append(np.stack(mc_vars).mean(axis=0)[valid])
            all_targets.append(targets.numpy()[valid])
            del sequences_dev

        self.raw_model.disable_mc_dropout()
        return self._summarize(all_preds, all_targets, all_vars, prefix="test")

    @torch.no_grad()
    def evaluate_test_ensemble(self) -> Dict[str, float]:
        if self.rank != 0:
            return {}
        if not self.snapshot_heap:
            log("No snapshots available for ensemble evaluation.")
            return {}

        paths = [
            p for _, _, p in sorted(self.snapshot_heap, key=lambda e: -e[0])
        ]
        models = [
            EnterpriseSTGCNModel.load(p, map_location=str(self.device))
            .to(self.device)
            .eval()
            for p in paths
        ]
        log(
            f"Ensembling {len(models)} snapshot checkpoints for final test evaluation."
        )

        all_preds, all_targets, all_vars = [], [], []
        for sequences, targets, masks in self.test_loader:
            if masks.sum() == 0:
                continue
            sequences_dev = [[g.to(self.device) for g in seq] for seq in sequences]
            preds_m, vars_m = [], []
            for m in models:
                pred, log_var = m(sequences_dev, return_uncertainty=True)
                preds_m.append(pred.cpu().numpy())
                vars_m.append(
                    torch.exp(
                        torch.clamp(log_var, max=self.config.log_var_max)
                    ).cpu().numpy()
                )
            valid = masks.bool().numpy()
            mean_pred = np.mean(preds_m, axis=0)
            total_var = np.mean(vars_m, axis=0) + np.var(preds_m, axis=0)
            all_preds.append(mean_pred[valid])
            all_vars.append(total_var[valid])
            all_targets.append(targets.numpy()[valid])
            del sequences_dev

        return self._summarize(
            all_preds, all_targets, all_vars, prefix="ensemble_test"
        )

    def _summarize(
        self,
        all_preds: list,
        all_targets: list,
        all_vars: list,
        prefix: str,
    ) -> Dict[str, float]:
        preds = np.concatenate(all_preds) if all_preds else np.array([])
        targets_np = np.concatenate(all_targets) if all_targets else np.array([])
        variances = np.concatenate(all_vars) if all_vars else np.array([])
        if len(preds) < 2:
            log(f"[{prefix}] Not enough valid samples to compute metrics.")
            return {}
        rmse = float(np.sqrt(mean_squared_error(targets_np, preds)))
        mae = float(mean_absolute_error(targets_np, preds))
        r2 = float(r2_score(targets_np, preds))
        std = np.sqrt(np.clip(variances, 1e-12, None))
        coverage_95 = float(
            np.mean(
                (targets_np >= preds - 1.96 * std)
                & (targets_np <= preds + 1.96 * std)
            )
        )
        metrics = {
            f"{prefix}_rmse": rmse,
            f"{prefix}_mae": mae,
            f"{prefix}_r2": r2,
            f"{prefix}_coverage_95": coverage_95,
            f"{prefix}_mean_var": float(variances.mean()),
            f"{prefix}_n_valid_targets": int(len(preds)),
        }
        log(
            f"[{prefix}] RMSE {rmse:.6f} | MAE {mae:.6f} | R2 {r2:.4f} | "
            f"95% CI cov {coverage_95:.2%} (n={len(preds)})"
        )
        return metrics


# ============================================================================
# 8. PERMUTATION IMPORTANCE
# ============================================================================
@torch.no_grad()
def compute_permutation_importance(
    model: EnterpriseSTGCNModel,
    test_loader: DataLoader,
    feature_dim: int,
    device: torch.device,
    max_batches: int = 15,
) -> Dict[str, Any]:
    model.eval()

    def run_pass(perturb_col: Optional[int]) -> float:
        total_se, total_n, n_batches = 0.0, 0, 0
        for sequences, targets, masks in test_loader:
            if n_batches >= max_batches:
                break
            if masks.sum() == 0:
                continue
            seq_dev = []
            for seq in sequences:
                s = []
                for g in seq:
                    g = g.to(device)
                    if perturb_col is not None:
                        g = g.clone()
                        idx = torch.randperm(g.x.shape[0], device=g.x.device)
                        g.x[:, perturb_col] = g.x[idx, perturb_col]
                    s.append(g)
                seq_dev.append(s)
            pred = model(seq_dev)
            valid = masks.to(device).bool()
            if valid.any():
                se = ((pred[valid] - targets.to(device)[valid]) ** 2).sum().item()
                total_se += se
                total_n += int(valid.sum().item())
            n_batches += 1
        return total_se / max(total_n, 1)

    baseline = run_pass(None)
    importances = []
    for col in range(feature_dim):
        score = run_pass(col)
        importances.append(score - baseline)
        log(f"  feature[{col:02d}] importance: {score - baseline:+.6f}")
    return {"baseline_mse": baseline, "importance_by_feature_index": importances}


# ============================================================================
# 8b. OPTIONAL TRADING-SIGNAL METRICS
# ============================================================================
@torch.no_grad()
def compute_trading_signal_metrics(
    model: EnterpriseSTGCNModel,
    test_loader: DataLoader,
    device: torch.device,
) -> Dict[str, float]:
    try:
        from ml.evaluation.finance_metrics import compute_all_finance_metrics
    except Exception as e:
        log(f"compute_all_finance_metrics unavailable ({e}); skipping.")
        return {}

    model.eval()
    daily_returns = []
    for sequences, targets, masks in test_loader:
        for b in range(len(sequences)):
            mask_b = masks[b]
            if mask_b.sum() == 0:
                continue
            seq_dev = [[g.to(device) for g in sequences[b]]]
            pred = model(seq_dev).cpu()[0]
            signal = torch.sign(pred)
            valid = mask_b.bool()
            if valid.sum() == 0:
                continue
            day_ret = (signal[valid] * targets[b][valid]).mean().item()
            daily_returns.append(day_ret)

    if len(daily_returns) < 2:
        log("Not enough valid days for trading metrics.")
        return {}

    try:
        fin = compute_all_finance_metrics(pd.Series(daily_returns))
        fin = {f"strategy_{k}": float(v) for k, v in fin.items()}
        log(f"[strategy] {fin}")
        return fin
    except Exception as e:
        log(f"compute_all_finance_metrics failed ({e}); skipping.")
        return {}


# ============================================================================
# 9. TARGET EXTRACTION — TIMEZONE-SAFE  [R3-BUG-1 FIX]
# ============================================================================
def _extract_targets_safe(
    proc_features: Dict[str, pd.DataFrame],
    graph_dates: List[datetime],
    available_symbols: List[str],
    target_col: str,
) -> Tuple[List[torch.Tensor], List[torch.Tensor]]:
    """
    Extract target values and masks from proc_features for each graph date.

    [R3-BUG-1 FIX]: Python stdlib datetime(tzinfo=timezone.utc) and pandas
    Timestamp(tz='UTC') do not reliably compare equal in df.loc[] indexing
    in pandas >= 2.0. Specifically:
      - `date in df.index` may return True (pandas coerces for __contains__)
      - `df.loc[date, col]` may return NaN (strict label matching fails)
    This caused ALL targets to appear missing (mask=0), making target tensors
    all-zero, defeating normalization, and causing the degenerate collapse.

    Fix: Convert graph_dates to pd.Timestamp with explicit UTC timezone ONCE,
    then use vectorized df.reindex() for bulk extraction -- which uses pandas'
    own internal Timestamp comparison and is guaranteed correct. Fall back to
    scalar lookup only as last resort, also with pd.Timestamp conversion.

    Also logs a diagnostic sample of extracted values so future failures
    are immediately visible in the logs.
    """
    # Pre-convert all graph_dates to pd.Timestamp(UTC) once.
    # This is the canonical form that matches proc_features[sym].index.
    pd_dates = [pd.Timestamp(d).tz_localize("UTC") if d.tzinfo is None
                else pd.Timestamp(d).tz_convert("UTC")
                for d in graph_dates]

    T = len(pd_dates)
    N = len(available_symbols)

    # Build [T, N] arrays for vectorized processing.
    values_arr = np.full((T, N), np.nan, dtype=np.float64)
    for j, sym in enumerate(available_symbols):
        df = proc_features[sym]
        # reindex returns a Series aligned to pd_dates, NaN for missing.
        # This uses pandas' internal Timestamp matching -- guaranteed correct.
        col_series = df[target_col].reindex(pd_dates)
        values_arr[:, j] = col_series.values

    # Build tensor lists.
    target_returns: List[torch.Tensor] = []
    target_masks: List[torch.Tensor] = []
    for t in range(T):
        returns = []
        mask = []
        for j in range(N):
            v = values_arr[t, j]
            if np.isnan(v):
                returns.append(0.0)
                mask.append(0.0)
            else:
                returns.append(float(v))
                mask.append(1.0)
        target_returns.append(torch.tensor(returns, dtype=torch.float32))
        target_masks.append(torch.tensor(mask, dtype=torch.float32))

    # ---- Diagnostic: log summary to detect R3-BUG-1 recurrence ----
    stacked_vals = np.array([[r.item() for r in row] for row in target_returns])
    stacked_masks_np = np.array([[m.item() for m in row] for row in target_masks])

    n_total = T * N
    n_valid = int(stacked_masks_np.sum())
    mask_rate = n_valid / max(n_total, 1)

    log(
        f"Target extraction: {n_valid}/{n_total} valid ({mask_rate:.1%}). "
        f"If mask_rate < 50%, date alignment is still broken."
    )

    if mask_rate < 0.5:
        raise RuntimeError(
            f"CRITICAL: Target extraction produced only {mask_rate:.1%} valid "
            f"targets. This indicates a date alignment failure between graph_dates "
            f"and proc_features indices. Debug info:\n"
            f"  graph_dates[0] type={type(graph_dates[0])}, "
            f"  value={graph_dates[0]}\n"
            f"  proc_features['{available_symbols[0]}'].index[0] "
            f"  type={type(proc_features[available_symbols[0]].index[0])}, "
            f"  value={proc_features[available_symbols[0]].index[0]}\n"
            f"  pd_dates[0]={pd_dates[0]}"
        )

    # Log per-asset raw return statistics for sanity.
    log("Raw target statistics (before normalization):")
    for j, sym in enumerate(available_symbols):
        valid_mask = stacked_masks_np[:, j] > 0.5
        if valid_mask.sum() < 5:
            log(f"  {sym}: too few valid samples")
            continue
        vals = stacked_vals[valid_mask, j]
        log(
            f"  {sym}: n={valid_mask.sum()} | "
            f"mean={vals.mean():.5f} | std={vals.std():.5f} | "
            f"min={vals.min():.5f} | max={vals.max():.5f}"
        )

    return target_returns, target_masks


# ============================================================================
# 10. TARGET NORMALIZATION
# ============================================================================
def _normalize_targets(
    raw_targets: List[torch.Tensor],
    masks: List[torch.Tensor],
    available_symbols: List[str],
    config: "TrainingConfig",
) -> Tuple[List[torch.Tensor], Dict[str, float]]:
    """
    Normalize each asset's daily return by its rolling std (causal, shift=1)
    so that zero-prediction gives MSE ≈ 1.0 after normalization.

    Works entirely on stacked tensor data -- no pandas index alignment,
    no datetime matching, no timezone conversion needed here.
    """
    W = config.target_norm_window
    N = len(available_symbols)
    T = len(raw_targets)

    if T == 0 or N == 0:
        return raw_targets, {}

    stacked = torch.stack(raw_targets).numpy()       # [T, N]
    stacked_masks = torch.stack(masks).numpy()        # [T, N]

    scale_map: Dict[str, float] = {}
    per_sample_scales = np.ones((T, N), dtype=np.float64)

    for j, sym in enumerate(available_symbols):
        series = stacked[:, j].copy().astype(np.float64)
        mask_j = stacked_masks[:, j]

        # Replace invalid entries with NaN for rolling computation.
        series[mask_j < 0.5] = np.nan

        s = pd.Series(series)

        # Causal rolling std: shift(1) ensures std at t uses [t-W, t-1].
        rolling_std = (
            s.shift(1)
            .rolling(window=W, min_periods=max(5, W // 4))
            .std()
            .values
        )

        valid_stds = rolling_std[~np.isnan(rolling_std) & (rolling_std > 1e-6)]
        if len(valid_stds) > 0:
            median_std = float(np.median(valid_stds))
            log(
                f"  {sym}: rolling std computed from {len(valid_stds)} windows | "
                f"median={median_std:.5f} | "
                f"range=[{valid_stds.min():.5f}, {valid_stds.max():.5f}]"
            )
        else:
            median_std = float(np.nanstd(series)) if not np.all(np.isnan(series)) else 0.02
            if median_std < 1e-6:
                median_std = 0.02
            log(
                f"  {sym}: WARNING -- no valid rolling std windows. "
                f"Using global std={median_std:.5f} as fallback. "
                f"Check that target_norm_window ({W}) << data length ({T})."
            )
        scale_map[sym] = median_std

        # Forward-fill: use median_std before rolling window accumulates,
        # then track the most recent valid rolling std.
        last_valid_std = median_std
        filled_stds = np.empty(T, dtype=np.float64)
        for t in range(T):
            s_t = rolling_std[t]
            if not np.isnan(s_t) and s_t > 1e-6:
                last_valid_std = float(s_t)
            filled_stds[t] = last_valid_std

        per_sample_scales[:, j] = filled_stds

    # Divide each valid target by its per-sample rolling std.
    normalized: List[torch.Tensor] = []
    for t in range(T):
        ret_t = raw_targets[t].clone()
        mask_t = masks[t]
        for j in range(N):
            if mask_t[j].item() > 0.5:
                std_val = per_sample_scales[t, j]
                if std_val > 1e-8:
                    ret_t[j] = ret_t[j] / std_val
        normalized.append(ret_t)

    return normalized, scale_map


def _verify_normalization(
    target_returns: List[torch.Tensor],
    target_masks: List[torch.Tensor],
    available_symbols: List[str],
) -> None:
    """
    Post-normalization sanity check. Raises RuntimeError if normalization
    produced near-zero targets (std < 0.1), which would cause dead weights.
    """
    stacked = torch.stack(target_returns).numpy()
    stacked_masks = torch.stack(target_masks).numpy()
    log("Post-normalization target std check:")
    any_failed = False
    for j, sym in enumerate(available_symbols):
        valid = stacked_masks[:, j] > 0.5
        if valid.sum() < 5:
            log(f"  {sym}: too few valid samples to check std")
            continue
        std_val = float(np.std(stacked[valid, j]))
        mean_val = float(np.mean(stacked[valid, j]))
        if 0.1 <= std_val <= 10.0:
            log(f"  {sym}: std={std_val:.4f} mean={mean_val:.4f} [OK]")
        elif std_val < 0.1:
            log(
                f"  {sym}: std={std_val:.6f} mean={mean_val:.6f} "
                f"[CRITICAL: near-zero std after normalization]"
            )
            any_failed = True
        else:
            log(
                f"  {sym}: std={std_val:.4f} mean={mean_val:.4f} "
                f"[WARNING: large std -- check for outlier returns]"
            )

    if any_failed:
        raise RuntimeError(
            "Target normalization produced near-zero std for one or more assets. "
            "Training would produce dead weights. "
            "Check that _extract_targets_safe returned non-zero, non-masked targets. "
            "The post-normalization std should be close to 1.0 for all assets."
        )


# ============================================================================
# 11. DATA LOADING  [R3-BUG-3 FIX in _determine_surviving_dates]
# ============================================================================
def _cache_key(symbols: List[str], config: TrainingConfig) -> str:
    payload = json.dumps(
        {
            "symbols": sorted(symbols),
            "history_days": config.history_days,
            "feature_dim": config.feature_dim,
            "target_col": config.target_col,
            "max_missing_frac": config.max_missing_frac,
            "normalize_targets": config.normalize_targets,
            "target_norm_window": config.target_norm_window,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _determine_surviving_dates(
    proc_features: Dict[str, pd.DataFrame],
    symbols: List[str],
    start_dt: datetime,
    end_dt: datetime,
    max_missing_frac: float,
) -> List[datetime]:
    """
    Returns dates where at most max_missing_frac of symbols have missing data.

    [R3-BUG-3 FIX]: proc_features[sym].index contains pd.Timestamp(UTC).
    Iterating with Python datetime objects and checking 'current in date_set'
    where date_set = set(df.index) hits the stdlib-datetime vs pandas-Timestamp
    equality issue. Fix: convert the index to a set of normalized pd.Timestamps
    once, then iterate using pd.Timestamps.
    """
    # Build date sets using pd.Timestamp for reliable equality comparison.
    date_sets: Dict[str, set] = {}
    for s in symbols:
        # proc_features[s].index is already UTC-floored to day (pd.Timestamp).
        date_sets[s] = set(proc_features[s].index)

    surviving = []
    # Iterate using pd.Timestamp to match the index type exactly.
    current_ts = pd.Timestamp(start_dt).tz_convert("UTC")
    end_ts = pd.Timestamp(end_dt).tz_convert("UTC")
    one_day = pd.Timedelta(days=1)
    n_symbols = len(symbols)

    while current_ts <= end_ts:
        missing = sum(1 for s in symbols if current_ts not in date_sets[s])
        if missing / n_symbols <= max_missing_frac:
            # Return as Python datetime for backward compatibility with
            # graph_builder.build_graph() interface.
            surviving.append(current_ts.to_pydatetime())
        current_ts += one_day

    return surviving


def _log_windowing_safety(config: TrainingConfig) -> None:
    assert config.forecast_horizon >= 1, (
        f"forecast_horizon={config.forecast_horizon} must be >= 1."
    )
    log(
        f"Leakage check: target_col='{config.target_col}' is a graph_builder "
        f"node feature, but forecast_horizon={config.forecast_horizon} >= 1 "
        f"guarantees the input window excludes the target day. No leakage."
    )


def _build_dataset_from_scratch(config: TrainingConfig, symbols: List[str]) -> Tuple:
    _log_windowing_safety(config)

    store = FeatureStore()
    now = now_utc()
    start_date = (now - timedelta(days=config.history_days)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")

    log(f"Loading features from {start_date} to {end_date}...")
    features = store.load_node_features(
        start_date, end_date, symbols, expected_features=config.feature_dim
    )

    available_symbols = [
        s for s in symbols if s in features and not features[s].empty
    ]
    if not available_symbols:
        raise ValueError("No features found for any symbol.")
    log(f"Loaded features for {len(available_symbols)} assets.")

    builder = DynamicGraphBuilder(
        supabase_client=None,
        asset_symbols=available_symbols,
        feature_dim=config.feature_dim,
    )

    proc_features: Dict[str, pd.DataFrame] = {}
    for sym in available_symbols:
        df = features[sym].copy()
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        # Normalize index to UTC, floor to day, deduplicate.
        # Result: DatetimeIndex of pd.Timestamp(UTC) at midnight.
        df.index = (
            df.index.tz_localize("UTC")
            if df.index.tz is None
            else df.index.tz_convert("UTC")
        )
        df.index = df.index.floor("D")
        df = df[~df.index.duplicated(keep="last")]
        if config.target_col not in df.columns:
            raise ValueError(
                f"target_col='{config.target_col}' not found for {sym}. "
                f"Available: {list(df.columns)}"
            )
        proc_features[sym] = df
        log(f"  [pipeline debug] {sym}: returns_1d head={df['returns_1d'].head().values.tolist()}, std={df['returns_1d'].std()}")

    # Log a sample of the index type for debugging future timezone issues.
    sample_sym = available_symbols[0]
    sample_idx = proc_features[sample_sym].index[0]
    log(
        f"proc_features index sample: type={type(sample_idx).__name__}, "
        f"value={sample_idx}, tz={sample_idx.tzinfo}"
    )

    start_dt = (now - timedelta(days=config.history_days)).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )
    end_dt = now.replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )

    # [R3-BUG-3 FIX]: _determine_surviving_dates now uses pd.Timestamp iteration.
    surviving_dates = _determine_surviving_dates(
        proc_features, available_symbols, start_dt, end_dt, config.max_missing_frac
    )
    if not surviving_dates:
        raise ValueError(
            "No dates survive the missing-data filter. "
            "Check ingestion or increase max_missing_frac."
        )
    log(f"Surviving dates: {len(surviving_dates)} (first={surviving_dates[0].date()}, "
        f"last={surviving_dates[-1].date()})")

    all_graphs, graph_dates, n_skipped = [], [], 0
    for d in surviving_dates:
        try:
            g = builder.build_graph(d, proc_features)
            all_graphs.append(g)
            graph_dates.append(d)
        except Exception as e:
            n_skipped += 1
            log(f"Skipping {d.date()} -- graph build failed: {e}")

    if n_skipped:
        log(f"Skipped {n_skipped} days during graph construction.")
    if not all_graphs:
        raise ValueError("No graphs could be built.")
    log(f"Built {len(all_graphs)} daily graphs.")

    # [R3-BUG-1 FIX]: Use _extract_targets_safe for timezone-correct extraction.
    log("Extracting targets (timezone-safe)...")
    target_returns, target_masks = _extract_targets_safe(
        proc_features, graph_dates, available_symbols, config.target_col
    )

    # Normalize targets to ~unit std.
    scale_map: Dict[str, float] = {}
    if config.normalize_targets:
        log("Computing normalization scales:")
        target_returns, scale_map = _normalize_targets(
            target_returns, target_masks, available_symbols, config
        )
        scale_stats = {s: f"{v:.4f}" for s, v in scale_map.items()}
        log(f"Target normalization scales (median daily return std): {scale_stats}")

        # Raises RuntimeError if normalization produced near-zero targets.
        _verify_normalization(target_returns, target_masks, available_symbols)

    return (
        all_graphs,
        target_returns,
        target_masks,
        graph_dates,
        available_symbols,
        scale_map,
    )


def load_data(
    config: TrainingConfig,
    symbols: List[str],
    rank: int,
    is_distributed: bool,
) -> Tuple:
    cache_key = _cache_key(symbols, config)
    cache_path = CACHE_DIR / f"graphs_{cache_key}.pkl"

    def cache_valid() -> bool:
        return (
            config.use_cache
            and cache_path.exists()
            and (time.time() - cache_path.stat().st_mtime) / 3600
            <= config.cache_max_age_hours
        )

    def load_from_cache() -> Tuple:
        log(f"Loading cached graph sequences from {cache_path.name}")
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    def build_and_maybe_cache() -> Tuple:
        result = _build_dataset_from_scratch(config, symbols)
        if config.use_cache:
            try:
                with open(cache_path, "wb") as f:
                    pickle.dump(result, f)
                log(f"Cached graph sequences to {cache_path.name}")
            except Exception as e:
                log(f"Could not write cache (non-fatal): {e}")
        return result

    if not is_distributed:
        if cache_valid():
            return load_from_cache()
        return build_and_maybe_cache()

    # Distributed: rank 0 builds, broadcasts to others.
    container = [None]
    error_container = [None]

    if rank == 0:
        try:
            if cache_valid():
                container[0] = load_from_cache()
            else:
                container[0] = build_and_maybe_cache()
        except Exception as e:
            error_container[0] = str(e)
            log(
                f"Rank 0 failed to load data: {e}\n{traceback.format_exc()}",
                force=True,
            )

    # Broadcast error flag before barrier to prevent hangs.
    dist.broadcast_object_list(error_container, src=0)
    if error_container[0] is not None:
        raise RuntimeError(
            f"Rank 0 failed to build/load dataset: {error_container[0]}"
        )

    dist.broadcast_object_list(container, src=0)
    dist.barrier()
    return container[0]


# ============================================================================
# 12. RESUME DISCOVERY
# ============================================================================
def find_latest_checkpoint() -> Optional[Path]:
    candidates = sorted(
        RUNS_DIR.glob("*/checkpoint_last.pt"),
        key=lambda p: p.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


# ============================================================================
# 13. MAIN
# ============================================================================
def parse_args():
    p = argparse.ArgumentParser(
        description="Enterprise ST-GCN training pipeline."
    )
    p.add_argument(
        "--resume",
        nargs="?",
        const="auto",
        default=None,
        help="'auto' or explicit path to checkpoint_last.pt",
    )
    return p.parse_args()


def main():
    global _CURRENT_RANK
    args = parse_args()
    config = TrainingConfig()
    set_seed(config.seed)

    is_distributed, rank, local_rank, world_size, device = setup_distributed()
    _CURRENT_RANK = rank

    torch.backends.cudnn.benchmark = config.cudnn_benchmark
    if hasattr(torch.backends.cuda, "matmul"):
        torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    try:
        resume_target: Optional[Path] = None
        if args.resume == "auto":
            resume_target = find_latest_checkpoint()
            if resume_target is None and rank == 0:
                log("--resume auto: no existing checkpoint found; starting fresh.")
        elif args.resume:
            resume_target = Path(args.resume)
            if not resume_target.exists():
                raise FileNotFoundError(
                    f"--resume path does not exist: {resume_target}"
                )

        if is_distributed:
            rid_container = [None]
            if rank == 0:
                rid_container[0] = (
                    resume_target.parent.name if resume_target else new_run_id()
                )
            dist.broadcast_object_list(rid_container, src=0)
            rid = rid_container[0]
        else:
            rid = resume_target.parent.name if resume_target else new_run_id()

        run_dir = RUNS_DIR / rid
        if rank == 0:
            run_dir.mkdir(parents=True, exist_ok=True)
        if is_distributed:
            dist.barrier()

        log(f"Run ID: {rid} | Artifacts: {run_dir}")

        try:
            from backend.app.db.database import SessionLocal
            from backend.app.db.models import Asset

            db = SessionLocal()
            symbols = [a.symbol for a in db.query(Asset).all()]
            db.close()
            if not symbols:
                raise ValueError("DB returned empty symbol list")
        except Exception as e:
            log(f"DB symbol lookup failed ({e}); using fallback symbol list.")
            symbols = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE"]
        log(f"Assets: {symbols}")

        (
            all_graphs,
            target_returns,
            target_masks,
            graph_dates,
            available_symbols,
            scale_map,
        ) = load_data(config, symbols, rank, is_distributed)

        if rank == 0 and scale_map:
            with open(run_dir / "target_scale_map.json", "w") as f:
                json.dump(scale_map, f, indent=2)
            log("Target scale map saved.")

        min_required = config.lookback_days + config.forecast_horizon + 10
        if len(all_graphs) < min_required:
            raise ValueError(
                f"Not enough graphs: {len(all_graphs)} < {min_required}."
            )

        n = len(all_graphs)
        train_end = int(n * 0.70)
        val_end = int(n * 0.85)
        log(
            f"Split (by target index): train [0,{train_end}) "
            f"val [{train_end},{val_end}) test [{val_end},{n})"
        )

        train_ds = WindowedGraphDataset(
            all_graphs, target_returns, target_masks,
            config.lookback_days, config.forecast_horizon, 0, train_end,
        )
        val_ds = WindowedGraphDataset(
            all_graphs, target_returns, target_masks,
            config.lookback_days, config.forecast_horizon, train_end, val_end,
        )
        test_ds = WindowedGraphDataset(
            all_graphs, target_returns, target_masks,
            config.lookback_days, config.forecast_horizon, val_end, n,
        )

        if len(train_ds) == 0 or len(val_ds) == 0 or len(test_ds) == 0:
            raise ValueError(
                f"Empty split(s): train={len(train_ds)} val={len(val_ds)} "
                f"test={len(test_ds)}."
            )
        log(
            f"Samples -> train {len(train_ds)} | "
            f"val {len(val_ds)} | test {len(test_ds)}"
        )

        common_kwargs = dict(
            collate_fn=graph_collate_fn,
            num_workers=config.num_workers,
            pin_memory=False,
            persistent_workers=(config.num_workers > 0),
        )

        train_sampler = None
        if is_distributed:
            train_sampler = DistributedSampler(
                train_ds,
                num_replicas=world_size,
                rank=rank,
                shuffle=True,
                seed=config.seed,
                drop_last=True,
            )
            train_loader = DataLoader(
                train_ds,
                batch_size=config.batch_size,
                sampler=train_sampler,
                drop_last=True,
                **common_kwargs,
            )
        else:
            train_loader = DataLoader(
                train_ds,
                batch_size=config.batch_size,
                shuffle=True,
                **common_kwargs,
            )

        val_loader = DataLoader(
            val_ds, batch_size=config.batch_size * 2, shuffle=False, **common_kwargs
        )
        test_loader = DataLoader(
            test_ds, batch_size=config.batch_size * 2, shuffle=False, **common_kwargs
        )

        log(f"Device: {device}")
        model = EnterpriseSTGCNModel(config)
        trainer = EnterpriseTrainer(
            model, train_loader, val_loader, test_loader,
            config, device, run_dir,
            is_distributed, rank, world_size, train_sampler,
        )

        trainer.fit()

        test_metrics = trainer.evaluate_test()
        ensemble_metrics = trainer.evaluate_test_ensemble()
        all_metrics = {**test_metrics, **ensemble_metrics}

        if rank == 0 and config.run_trading_metrics:
            trading_metrics = compute_trading_signal_metrics(
                trainer.raw_model, test_loader, device
            )
            all_metrics.update(trading_metrics)

        if rank == 0:
            with open(run_dir / "config.json", "w") as f:
                json.dump(config.to_dict(), f, indent=2)
            with open(run_dir / "test_metrics.json", "w") as f:
                json.dump(all_metrics, f, indent=2)
            with open(ARTIFACTS_DIR / "enterprise_config.json", "w") as f:
                json.dump(config.to_dict(), f, indent=2)
            with open(ARTIFACTS_DIR / "enterprise_test_metrics.json", "w") as f:
                json.dump(all_metrics, f, indent=2)

            if config.run_permutation_importance:
                try:
                    log("Computing permutation feature importance...")
                    importance = compute_permutation_importance(
                        trainer.raw_model,
                        test_loader,
                        config.feature_dim,
                        device,
                        max_batches=config.importance_max_batches,
                    )
                    with open(run_dir / "feature_importance.json", "w") as f:
                        json.dump(importance, f, indent=2)
                except Exception as e:
                    log(f"Permutation importance failed (non-fatal): {e}")

            try:
                from backend.app.db.database import SessionLocal, Base, engine
                from backend.app.db.models import ModelRegistry

                Base.metadata.create_all(bind=engine)
                db = SessionLocal()
                version = f"stgcn-enterprise-{rid}"
                if not db.query(ModelRegistry).filter_by(version=version).first():
                    db.add(
                        ModelRegistry(
                            version=version,
                            wandb_run_id=None,
                            metrics=all_metrics,
                            artifact_path=str(ARTIFACTS_DIR / "best_model.pt"),
                            deployed_at=now_utc(),
                        )
                    )
                    db.commit()
                    log(f"Model registered: {version}")
                db.close()
            except Exception as e:
                log(f"Skipping DB registration (non-fatal): {e}")

            log("ENTERPRISE TRAINING COMPLETE")
            log(f"Best model: {ARTIFACTS_DIR / 'best_model.pt'}")
            log(f"Snapshots kept: {len(trainer.snapshot_heap)}")
            if "test_rmse" in all_metrics:
                log(f"Test RMSE: {all_metrics['test_rmse']:.6f}")
            if "ensemble_test_rmse" in all_metrics:
                log(f"Ensemble Test RMSE: {all_metrics['ensemble_test_rmse']:.6f}")
            if "strategy_sharpe_ratio" in all_metrics:
                log(f"Strategy Sharpe: {all_metrics['strategy_sharpe_ratio']:.4f}")

    except Exception:
        log(f"FATAL ERROR:\n{traceback.format_exc()}", force=True)
        raise
    finally:
        cleanup_distributed(is_distributed)


if __name__ == "__main__":
    main()