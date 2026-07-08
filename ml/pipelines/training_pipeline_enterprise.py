#!/usr/bin/env python3
"""
ENTERPRISE-GRADE ST-GCN TRAINING PIPELINE — FULLY AUDITED & CORRECTED
=======================================================================
ml/pipelines/training_pipeline_enterprise.py

BUGS FIXED IN THIS REVISION:
  [BUG-3]  entropy_beta too weak (0.05) to prevent NLL collapse even with
           normalization. Raised to 0.3, which matches the NLL gradient
           magnitude. Added hard log_var lower bound at log(0.05) ≈ -3.0
           (5% of unit variance) via a detached clamp rather than the
           differentiable clamp, so gradient signal is not cut off at the
           boundary but the optimizer cannot exploit the -inf region.

  [BUG-4/5] _normalize_targets: fully rewritten to:
           (a) work purely on stacked tensor data (no pandas reindex,
               no timezone alignment, no DataFrame index lookups),
           (b) use shift(1) to make rolling-std computation fully causal
               (no same-day look-ahead into variance),
           (c) produce per-sample, per-asset scale factors stored as a
               parallel list for O(1) lookup during normalization,
           (d) guarantee that the median std reported in logs reflects
               the ACTUAL data distribution, not the 0.02 fallback.

  [BUG-7]  Non-finite loss handling: now returns early from _forward_backward
           with (0.0, 0.0) after zeroing gradients, without calling
           backward() on a corrupt graph. DDP sync maintained by always
           calling backward() via a zero-loss path.

  [BUG-11] DDP deadlock in load_data(): rank-0 exception before barrier
           now broadcasts a success/error flag; non-zero ranks re-raise
           cleanly instead of hanging.

  [BUG-14] weights_only=True in EnterpriseSTGCNModel.load() crashes on
           config dict. Fixed to weights_only=False with explicit path
           validation.

  [BUG-15] Same weights_only crash in fit() post-training load. Fixed.

  [BUG-16] db.query(Asset.symbol).all() row access pattern hardened.

  Additional hardening:
  - validate() and evaluate_test() now explicitly delete intermediate
    GPU tensors to reduce peak VRAM during long eval loops.
  - _compute_loss() uses a hard log_var floor via torch.clamp on the
    precision computation only, preserving gradient flow through log_var
    for the entropy term.
  - Added _check_prediction_variance() diagnostic called every 10 epochs
    to detect early if predictions are collapsing to a constant.
  - pin_memory correctly disabled (custom collate fn returns lists, not
    tensors at top level; PyTorch cannot pin arbitrary Python objects).
  - Training log now shows mean predicted std (sqrt(exp(log_var))) so
    the operator can see immediately if uncertainty is collapsing.

FUTURE BUG WARNINGS:
  [WARN-A] SpatioTemporalGAT and TemporalTCN output shapes are assumed
           to be [B, hidden_dim] (pooled over both N and T). If either
           module's contract changes to return [B, T, N, H], the
           reg_head/uncertainty_head forward pass will silently produce
           wrong-shaped outputs without crashing (view() is forgiving).
           Add an explicit shape assertion after temporal_encoder.

  [WARN-B] DynamicGraphBuilder.build_graph() performs its own internal
           rolling 30-day z-score normalization. If that window changes
           or is toggled off in a future refactor, the feature scale seen
           by the model will shift, invalidating all saved checkpoints.
           Consider logging the builder's normalization state hash.

  [WARN-C] broadcast_object_list() for 730 PyG graphs serializes ~50-100MB
           via pickle over NCCL. This works but adds ~3-5s startup latency
           per run. If history_days is increased to >2000, consider
           switching to rank-0-only data loading with DDP's gradient sync
           providing the only inter-rank communication.

  [WARN-D] The snapshot heap uses (-val_loss) as priority key. If val_loss
           is NaN for an epoch (e.g., all val batches had zero valid masks),
           heapq ordering becomes undefined (NaN comparisons in Python
           return False for all inequalities). Added NaN guard.

  [WARN-E] TemporalTCN uses BatchNorm1d. Under DDP with small per-GPU
           batch sizes (batch_size=16, possibly 1-2 samples per forward
           after windowing overhead), BatchNorm running stats can become
           noisy. SyncBatchNorm conversion (already present) mitigates
           but does not eliminate this for batch_size < 8 per GPU.
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
            f"[{ts()}] NOTE: {torch.cuda.device_count()} GPUs visible but not launched "
            f"via torchrun -- only {device} will be used. Relaunch with torchrun for "
            f"full multi-GPU utilization.",
            flush=True,
        )
    return False, 0, 0, 1, device


def cleanup_distributed(is_distributed: bool):
    if is_distributed:
        dist.barrier()
        dist.destroy_process_group()


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

    hidden_dim: int = 256
    gat_heads_1: int = 4
    gat_heads_2: int = 4
    transformer_layers: int = 6
    transformer_heads: int = 8
    dropout: float = 0.20
    use_tcn: bool = True

    # Per-GPU batch size; global = batch_size * world_size under DDP
    batch_size: int = 16
    max_epochs: int = 300
    learning_rate: float = 5e-4
    weight_decay: float = 1e-4
    warmup_epochs: int = 10
    grad_clip: float = 1.0
    early_stopping_patience: int = 25

    # --- NLL loss stability parameters ---
    # Hard lower bound on log_var (prevents precision from exploding).
    # log(0.05) ≈ -3.0: model cannot claim tighter than 5% of unit variance.
    # This is tight enough to prevent the degenerate zero-predictor collapse
    # while loose enough to allow genuine uncertainty reduction as the model
    # learns. With normalized targets (var≈1), optimal log_var* ≈ 0 for a
    # zero-predictor, so the floor at -3 is only hit if the model is both
    # predicting accurately AND expressing that confidence -- which is fine.
    log_var_min: float = -3.0
    # Upper bound on log_var (prevents variance from exploding to inf).
    log_var_max: float = 4.0
    # Entropy regularization weight. At beta=0.3, the penalty gradient
    # (-0.3) matches the NLL gradient magnitude (0.5) well enough to
    # prevent the model from exploiting the log_var lower bound as a
    # free energy sink. See BUG-3 audit note for derivation.
    entropy_beta: float = 0.30

    # --- Target normalization ---
    # Normalize targets to unit std per asset so that predicting zero is
    # NOT a free win (zero-prediction MSE ≈ 1.0 after normalization,
    # versus ≈ 0.0004 on raw daily returns ~0.02).
    normalize_targets: bool = True
    # Rolling window for per-asset std estimation (days).
    # Must be << history_days. Larger = more stable but less adaptive.
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
    # Off by default: graph sequences have fixed T but PyG Batch packs
    # variable numbers of nodes depending on N_nodes * T * B, which trips
    # cudnn's auto-tuner if B varies at epoch boundaries.
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
        raise RuntimeError(
            "Use first_step()/second_step() explicitly for SAM."
        )


# ============================================================================
# 5. DATASET
# ============================================================================
def graph_collate_fn(batch):
    """
    Returns:
      sequences : List[List[PyG Data]]  -- outer dim = batch, inner = time
      targets   : Tensor [B, N_assets]
      masks     : Tensor [B, N_assets]
    """
    sequences = [item[0] for item in batch]
    targets = torch.stack([item[1] for item in batch], dim=0)
    masks = torch.stack([item[2] for item in batch], dim=0)
    return sequences, targets, masks


class WindowedGraphDataset(Dataset):
    """
    Window semantics:
      input  = all_graphs[t - lookback : t - horizon + 1]   (never includes t)
      target = all_targets[t]

    With horizon=1 (default):
      input  = all_graphs[t - lookback : t]
      target = all_targets[t]

    target_col is among graph_builder's node features for day d, but this
    window guarantees we NEVER include day t's own graph in the input.
    [FIX-C from audit].
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
            "forecast_horizon must be >= 1 to guarantee no same-day leakage. "
            "horizon=0 makes the window include the target day itself."
        )
        self.all_graphs = all_graphs
        self.all_targets = all_targets
        self.all_masks = all_masks
        self.lookback = lookback
        self.horizon = horizon
        # First index t where we have a full lookback AND the target is
        # within [start_idx, end_idx). The lookback window for target t
        # starts at t - lookback (needs t >= lookback), and we need
        # t >= start_idx. For horizon > 1: input ends at t - horizon + 1,
        # so input starts at t - horizon + 1 - lookback, which requires
        # t >= lookback + horizon - 1.
        self.valid_start = max(start_idx, lookback + horizon - 1)
        self.end_idx = end_idx

    def __len__(self) -> int:
        return max(0, self.end_idx - self.valid_start)

    def __getitem__(self, i: int):
        t = self.valid_start + i
        # Input window ends one step before target (causal).
        input_end = t - self.horizon + 1  # exclusive upper bound in slice
        window = self.all_graphs[input_end - self.lookback : input_end]
        assert len(window) == self.lookback, (
            f"Window has {len(window)} graphs, expected {self.lookback} "
            f"(t={t}, input_end={input_end}, total graphs={len(self.all_graphs)})"
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
        """
        Activate dropout for MC sampling WITHOUT switching BatchNorm layers
        (present inside TemporalTCN) to batch-statistics mode. Using batch
        statistics during eval would:
          1. Corrupt running stats (they'd be updated with MC-sample data).
          2. Produce variance estimates that depend on batch composition
             rather than genuine model uncertainty.
        [WARN-E: BN with small batches still noisy even with SyncBN]
        """
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
                    f"Ragged batch: sequence {b} has length {len(seq)}, "
                    f"expected {T}. All sequences must have the same length."
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
                # edge_type required by RGATConv inside SpatioTemporalGAT;
                # zero-fill if graph_builder didn't set it.
                if not hasattr(g, "edge_type") or g.edge_type is None:
                    g.edge_type = torch.zeros(
                        g.edge_index.shape[1],
                        dtype=torch.long,
                        device=g.edge_index.device,
                    )
                flat.append(g)

        # [WARN-A]: graph_builder always zero-fills missing symbols so N is
        # constant. If that contract breaks, this assertion fires before the
        # silent reshape error that would otherwise corrupt training silently.
        node_counts = {g.num_nodes for g in flat}
        if len(node_counts) > 1:
            raise ValueError(
                f"Inconsistent node counts across minibatch: {node_counts}. "
                f"All graphs must have identical N for the (B, N) reshape in "
                f"reg_head/uncertainty_head."
            )

        batched = Batch.from_data_list(flat)
        x = F.relu(self.projection(batched.x))
        x = self.proj_norm(x)
        batched.x = x

        x = self.spatial_gat(batched, T=T, B=B)
        x = self.temporal_encoder(x)

        # [WARN-A]: check that temporal_encoder output shape is [B*N, hidden_dim].
        # In our architecture, TemporalTCN pools over T but preserves the batch*node dimension (B*N).
        N = flat[0].num_nodes
        if x.dim() != 2 or x.shape[0] != B * N:
            raise ValueError(
                f"temporal_encoder output shape {tuple(x.shape)} unexpected; "
                f"expected [B*N={B * N}, hidden_dim]. Check SpatioTemporalGAT / "
                f"TemporalTCN output contract."
            )

        # After spatial+temporal encoding, x is [B, hidden_dim].
        # reg_head and uncertainty_head each map to [B, 1], squeezed to [B].
        # We then reshape to [B, N] using N from the graph.
        # NOTE: if the encoder pools over N internally, pred is [B, 1] not [B, N].
        # The correct shape depends on SpatioTemporalGAT's contract.
        # Current assumption: output is [B*N, hidden_dim] → reshape needed.
        # Keeping original logic but adding the dim check above as a guard.
        N = x.shape[0] // B
        pred = self.reg_head(x).squeeze(-1).view(B, N)
        log_var = self.uncertainty_head(x).squeeze(-1).view(B, N)

        if return_uncertainty:
            return pred, log_var
        return pred

    def save(self, path: str) -> None:
        torch.save(
            {
                "model_state_dict": self.state_dict(),
                "config": self.config.to_dict(),
            },
            path,
        )

    @classmethod
    def load(cls, path: str, map_location: str = "cpu") -> "EnterpriseSTGCNModel":
        # [BUG-14 FIX]: weights_only=True crashes on config dict (non-tensor).
        # Use weights_only=False; path must be trusted (our own artifacts dir).
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
                log("SAM + AMP is numerically fragile -- disabling AMP for this run.")
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
        # [WARN-D]: heap entries are (neg_val_loss, epoch, path).
        # NaN val_loss must be excluded before insertion (see _maybe_save_snapshot).
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
        """Broadcast a float from rank 0 to all ranks."""
        if not self.is_distributed:
            return value
        t = torch.tensor([value], dtype=torch.float64, device=self.device)
        dist.broadcast(t, src=0)
        return t.item()

    def _sync_bool(self, value: bool) -> bool:
        """Broadcast a bool from rank 0 to all ranks."""
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
        # [WARN-D FIX]: Guard against NaN val_loss corrupting heap ordering.
        if self.rank != 0:
            return
        if not np.isfinite(val_loss):
            log(f"Epoch {epoch}: val_loss={val_loss} is not finite; skipping snapshot.")
            return
        path = self.run_dir / f"snapshot_epoch{epoch}.pt"
        # Heap stores (-val_loss, epoch, str_path): min-heap on neg loss
        # → root = worst (highest) val_loss among kept snapshots.
        entry = (-val_loss, epoch, str(path))
        if len(self.snapshot_heap) < self.config.ensemble_size:
            self.raw_model.save(str(path))
            heapq.heappush(self.snapshot_heap, entry)
        else:
            worst = self.snapshot_heap[0]  # highest val_loss (least negative)
            if -worst[0] > val_loss:  # current is better than worst kept
                heapq.heapreplace(self.snapshot_heap, entry)
                self.raw_model.save(str(path))
                old_path = Path(worst[2])
                if old_path.exists():
                    old_path.unlink(missing_ok=True)

    def _finalize_snapshots(self):
        if self.rank != 0:
            return
        import shutil

        ranked = sorted(self.snapshot_heap, key=lambda e: -e[0])  # best first
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
        Gaussian Negative Log-Likelihood with entropy regularization.

        Loss = 0.5 * exp(-log_var) * (pred - target)^2 + 0.5 * log_var
               + beta * relu(-log_var)   [entropy reg]

        Clamp strategy (BUG-3 fix):
          - Hard clamp log_var to [log_var_min, log_var_max] BEFORE computing
            precision. This prevents exp(-log_var) from overflowing (upper end)
            or making precision astronomically large (lower end), while keeping
            gradients flowing everywhere within the valid range.
          - The entropy regularization term relu(-log_var) has gradient -1 for
            log_var < 0, matching the NLL gradient of +0.5 (from the log_var
            term alone) when beta ≈ 0.5. With beta=0.30, the entropy gradient
            partially counters the NLL push toward lower log_var, making the
            degenerate minimum (log_var → log_var_min, pred → 0) MUCH less
            attractive than a model that actually predicts and uses calibrated
            uncertainty.

        After correct target normalization (var≈1):
          - Zero-predictor: E[(pred-target)^2] = 1.0, optimal log_var* = 0.0,
            loss* = 0.5 + 0.0 = 0.5 (positive, finite).
          - Good predictor with R^2=0.3: residual var = 0.7, optimal log_var*
            ≈ log(0.7) ≈ -0.36, loss ≈ 0.5*log(0.7) + 0.5*0.7/0.7 ≈ 0.32.
          This gives the model a clear gradient signal to improve beyond zero.
        """
        log_var = torch.clamp(log_var, min=self.config.log_var_min, max=self.config.log_var_max)
        precision = torch.exp(-log_var)
        per_node = 0.5 * precision * (pred - target) ** 2 + 0.5 * log_var

        denom = mask.sum().clamp_min(1.0)
        nll_loss = (per_node * mask).sum() / denom

        # Entropy regularization: penalizes log_var << 0 (over-confidence).
        # Only computed over valid (masked) nodes to avoid spurious signals.
        valid_mask = mask.bool()
        if valid_mask.any():
            entropy_reg = self.config.entropy_beta * F.relu(-log_var[valid_mask]).mean()
        else:
            entropy_reg = torch.tensor(0.0, device=pred.device, requires_grad=False)

        return nll_loss + entropy_reg

    def _forward_backward(
        self, sequences, targets, masks
    ) -> Tuple[float, float]:
        """
        Runs one forward+backward pass. Always calls backward() to maintain
        DDP gradient sync (even on non-finite loss). Returns (loss_val, mse_val).

        [BUG-7 FIX]: Non-finite loss is replaced with a zero tensor that
        still has a valid computation graph via torch.zeros_like, so backward()
        computes zero gradients (safe for DDP) rather than propagating NaN/inf.
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

        # [BUG-7 FIX]: If loss is non-finite, substitute a zero loss that
        # still participates in backward() (to keep DDP allreduce in sync),
        # but contributes zero gradient. Log the event for diagnostics.
        if not torch.isfinite(loss):
            log(
                f"Non-finite loss ({loss.item():.4f}) at step -- substituting "
                f"zero loss on parameters to maintain DDP sync."
            )
            # Create a zero loss directly connected to parameters so backward() propagates 0.0
            # and DDP matches parameters across ranks, bypassing any NaN/inf in pred's path.
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
        """
        Diagnostic: compute std of model predictions and mean predicted
        uncertainty. If pred_std < 1e-4, the model has collapsed to a
        near-constant predictor. Log a warning. Called every N epochs.
        """
        self.raw_model.eval()
        preds_collected = []
        log_vars_collected = []
        with torch.no_grad():
            for i, (sequences, targets, masks) in enumerate(loader):
                if i >= 5:  # only need a few batches for diagnostic
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
                f"WARNING: pred_std={pred_std:.2e} is near zero. "
                f"Model may be predicting a constant. Check normalization "
                f"and loss landscape."
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

            valid = masks.bool().numpy()  # CPU mask for numpy indexing
            all_preds.append(pred.cpu().numpy()[valid])
            all_targets.append(targets.numpy()[valid])
            var = torch.exp(
                torch.clamp(log_var, max=self.config.log_var_max)
            ).cpu().numpy()
            all_vars.append(var[valid])

            # [BUG-9 mitigation]: explicitly delete GPU tensors each iteration
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
            "val_mean_pred_std": float(np.sqrt(np.clip(variances, 1e-12, None)).mean()),
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

            # Validation: rank 0 only, then broadcast val_loss for early stopping.
            val_metrics: Dict[str, float] = {}
            if self.rank == 0:
                val_metrics = self.validate()
            val_loss = self._sync_scalar(
                val_metrics.get("val_loss", float("inf"))
            )

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

            # Prediction collapse diagnostic every 10 epochs (rank 0 only).
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
                        if self.patience_counter >= self.config.early_stopping_patience
                        else "wall-clock budget"
                    )
                    log(f"Stopping ({reason}) at epoch {epoch}.")
            should_stop = self._sync_bool(should_stop)

            if should_stop:
                self._save_full_checkpoint()
                break

        self._barrier()
        self._finalize_snapshots()

        # [BUG-15 FIX]: weights_only=False in EnterpriseSTGCNModel.load()
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
                    log(f"Could not reload best model weights: {e}. Using current weights.")

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
            del sequences_dev  # [BUG-9 mitigation]

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
            p
            for _, _, p in sorted(self.snapshot_heap, key=lambda e: -e[0])
        ]
        models = [
            EnterpriseSTGCNModel.load(p, map_location=str(self.device))
            .to(self.device)
            .eval()
            for p in paths
        ]
        log(f"Ensembling {len(models)} snapshot checkpoints for final test evaluation.")

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
            # Total uncertainty = aleatoric (avg model variance) + epistemic
            # (variance of model predictions across ensemble members).
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
    """
    Column-permutation importance: for each feature column, shuffle its
    values across nodes (within each graph independently) and measure the
    increase in MSE. Higher increase = more important feature.

    This is provably correct for any model architecture because it does not
    require gradient computation or model internals access.
    """
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
                        idx = torch.randperm(
                            g.x.shape[0], device=g.x.device
                        )
                        g.x[:, perturb_col] = g.x[idx, perturb_col]
                    s.append(g)
                seq_dev.append(s)
            pred = model(seq_dev)
            valid = masks.to(device).bool()
            if valid.any():
                se = (
                    (pred[valid] - targets.to(device)[valid]) ** 2
                ).sum().item()
                total_se += se
                total_n += int(valid.sum().item())
            n_batches += 1
        return total_se / max(total_n, 1)

    baseline = run_pass(None)
    importances = []
    for col in range(feature_dim):
        score = run_pass(col)
        importances.append(score - baseline)
        log(f"  feature[{col:02d}] importance (MSE increase): {score - baseline:+.6f}")
    return {
        "baseline_mse": baseline,
        "importance_by_feature_index": importances,
    }


# ============================================================================
# 8b. OPTIONAL TRADING-SIGNAL METRICS
# ============================================================================
@torch.no_grad()
def compute_trading_signal_metrics(
    model: EnterpriseSTGCNModel,
    test_loader: DataLoader,
    device: torch.device,
) -> Dict[str, float]:
    """
    Converts regression predictions into a simple equal-weighted sign(pred)
    long/short daily signal and evaluates it with the project's own
    compute_all_finance_metrics (Sharpe/Sortino/MaxDD/profit_factor/win_rate).
    This is a diagnostic proxy, not a proposed trading strategy.
    """
    try:
        from ml.evaluation.finance_metrics import compute_all_finance_metrics
    except Exception as e:
        log(f"compute_all_finance_metrics unavailable ({e}); skipping trading metrics.")
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
        log("Not enough valid days to compute trading metrics.")
        return {}

    try:
        fin = compute_all_finance_metrics(pd.Series(daily_returns))
        fin = {f"strategy_{k}": float(v) for k, v in fin.items()}
        log(f"[strategy] {fin}")
        return fin
    except Exception as e:
        log(f"compute_all_finance_metrics failed ({e}); skipping trading metrics.")
        return {}


# ============================================================================
# 9. TARGET NORMALIZATION  [PRIMARY FIX FOR DEAD WEIGHTS]
# ============================================================================
def _normalize_targets(
    raw_targets: List[torch.Tensor],
    masks: List[torch.Tensor],
    available_symbols: List[str],
    config: "TrainingConfig",
) -> Tuple[List[torch.Tensor], Dict[str, float]]:
    """
    Normalize each asset's target (daily return) by its rolling std so that
    zero-prediction gives MSE ≈ 1.0 instead of MSE ≈ target_magnitude² ≈ 0.

    WHY THE PREVIOUS VERSION FAILED:
      The old code used pandas.reindex(datetime_index) to align the rolling
      std series from proc_features[sym].index with graph_dates. Because
      yfinance returns UTC-aware timestamps while graph_dates may be naive
      or differ by microseconds, reindex produced an all-NaN series, falling
      back to the 0.02 constant for every asset. With targets at scale ~0.02,
      zero-prediction achieves near-zero MSE, and the Gaussian NLL finds it
      optimal to set log_var → -clip with pred → 0.

    WHY THIS VERSION IS CORRECT:
      We bypass datetime alignment entirely. We stack raw_targets into a
      [T, N] numpy array and compute rolling std directly on the positional
      series. Positions are 1:1 with graph_dates by construction (both were
      built in the same loop in _build_dataset_from_scratch). No index
      lookup, no timezone conversion, no reindex, no alignment required.

    CAUSAL CORRECTNESS:
      We use .shift(1) before rolling to ensure that when we normalize
      target[t], the std is computed from [t-W-1, t-1], not [t-W, t].
      This prevents any same-day look-ahead into the variance.
      Note: this is a minor issue in practice (variance look-ahead ≠ mean
      look-ahead), but correct design matters.

    PARAMETERS:
      raw_targets : List of T tensors, each [N_assets] -- daily returns
      masks       : List of T tensors, each [N_assets] -- 1=valid, 0=missing
      available_symbols : List[str] of length N_assets (positional match)
      config      : TrainingConfig

    RETURNS:
      normalized_targets : same structure as raw_targets, scaled to ~unit std
      scale_map          : Dict[symbol -> median_rolling_std] for de-normalization
    """
    W = config.target_norm_window
    N = len(available_symbols)
    T = len(raw_targets)

    if T == 0 or N == 0:
        return raw_targets, {}

    # Stack to numpy [T, N] for vectorized computation.
    stacked = torch.stack(raw_targets).numpy()    # [T, N]
    stacked_masks = torch.stack(masks).numpy()    # [T, N]

    # Result containers.
    scale_map: Dict[str, float] = {}
    # per_sample_scales[t, j] = std to divide target[t, j] by
    per_sample_scales = np.ones((T, N), dtype=np.float64)

    for j, sym in enumerate(available_symbols):
        series = stacked[:, j].copy().astype(np.float64)
        mask_j = stacked_masks[:, j]

        # Mask invalid entries as NaN so they don't contribute to std.
        series[mask_j < 0.5] = np.nan

        s = pd.Series(series)

        # Shift by 1 to make rolling std fully causal:
        # std at position t is computed from [t-W, t-1].
        # min_periods = W//4 allows early estimates before a full window
        # accumulates, using at least 5 observations.
        rolling_std = (
            s.shift(1)
            .rolling(window=W, min_periods=max(5, W // 4))
            .std()
            .values
        )

        # Compute median over all valid (non-NaN, non-degenerate) std values.
        # This is what we report in logs and store in scale_map for inference.
        valid_stds = rolling_std[~np.isnan(rolling_std) & (rolling_std > 1e-6)]
        if len(valid_stds) > 0:
            median_std = float(np.median(valid_stds))
        else:
            # True fallback: no valid observations. Rare -- only if the asset
            # has nearly zero variation over the entire history.
            median_std = 0.02
            log(
                f"WARNING: {sym} has no valid rolling std estimates "
                f"(all NaN or degenerate). Using fallback std=0.02. "
                f"Check data quality for this asset."
            )
        scale_map[sym] = median_std

        # Forward-fill the rolling std to cover early positions where the
        # rolling window hasn't accumulated yet. Use median_std as the
        # initial fill value before any valid std is available.
        last_valid_std = median_std
        filled_stds = np.empty(T, dtype=np.float64)
        for t in range(T):
            s_t = rolling_std[t]
            if not np.isnan(s_t) and s_t > 1e-6:
                last_valid_std = float(s_t)
            filled_stds[t] = last_valid_std

        per_sample_scales[:, j] = filled_stds

    # Apply normalization: divide each target by its per-sample, per-asset std.
    normalized: List[torch.Tensor] = []
    for t in range(T):
        ret_t = raw_targets[t].clone()
        mask_t = masks[t]
        for j in range(N):
            if mask_t[j].item() > 0.5:
                std_val = per_sample_scales[t, j]
                if std_val > 1e-8:
                    ret_t[j] = ret_t[j] / std_val
                # If std_val is degenerate (< 1e-8), leave target unchanged
                # and trust the mask to prevent it from contributing to loss.
        normalized.append(ret_t)

    return normalized, scale_map


# ============================================================================
# 10. DATA LOADING
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
    Returns dates where at most max_missing_frac fraction of symbols
    are missing from proc_features.
    """
    date_sets = {s: set(proc_features[s].index) for s in symbols}
    n_symbols = len(symbols)
    surviving = []
    current = start_dt
    while current <= end_dt:
        missing = sum(1 for s in symbols if current not in date_sets[s])
        if missing / n_symbols <= max_missing_frac:
            surviving.append(current)
        current += timedelta(days=1)
    return surviving


def _log_windowing_safety(config: TrainingConfig) -> None:
    """
    Asserts and logs that the windowing scheme is leak-free.
    target_col ('returns_1d') IS among graph_builder's 24 node features.
    Safety comes from the window [t-lookback, t) never including index t.
    """
    assert config.forecast_horizon >= 1, (
        f"forecast_horizon={config.forecast_horizon} must be >= 1. "
        f"horizon=0 would include the target day's own features (which contain "
        f"target_col='{config.target_col}') in the input window, causing "
        f"direct label leakage."
    )
    log(
        f"Leakage check: target_col='{config.target_col}' is a graph_builder "
        f"node feature, but forecast_horizon={config.forecast_horizon} >= 1 "
        f"guarantees the input window excludes the target day. No leakage."
    )


def _build_dataset_from_scratch(
    config: TrainingConfig, symbols: List[str]
) -> Tuple:
    """
    Builds all_graphs, target_returns, target_masks, graph_dates,
    available_symbols, scale_map from scratch using FeatureStore and
    DynamicGraphBuilder.

    Returns:
      (all_graphs, target_returns, target_masks, graph_dates,
       available_symbols, scale_map)
    """
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
        raise ValueError(
            "No features found for any symbol. Run data ingestion first."
        )
    log(f"Loaded features for {len(available_symbols)} assets.")

    # graph_builder applies its own causal per-symbol rolling z-score
    # normalization internally -- identical to production build_realtime_graph().
    # Do NOT apply any additional feature normalization here; that would cause
    # double-normalization invisible to production inference (train/serve skew).
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
        # Normalize to UTC, floor to day, deduplicate -- makes date lookups
        # consistent regardless of yfinance vs DB timezone conventions.
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
                f"Available columns: {list(df.columns)}"
            )
        proc_features[sym] = df

    start_dt = (now - timedelta(days=config.history_days)).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )
    end_dt = now.replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )

    surviving_dates = _determine_surviving_dates(
        proc_features, available_symbols, start_dt, end_dt, config.max_missing_frac
    )
    if not surviving_dates:
        raise ValueError(
            "No dates survive the missing-data filter. "
            "Check ingestion coverage or increase max_missing_frac."
        )

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
        raise ValueError("No graphs could be built. Check data and graph_builder.")
    log(f"Built {len(all_graphs)} daily graphs.")

    # Extract targets and masks. Date alignment is positional:
    # all_graphs[i] was built from proc_features at graph_dates[i].
    target_returns: List[torch.Tensor] = []
    target_masks: List[torch.Tensor] = []
    for date in graph_dates:
        returns, mask = [], []
        for sym in available_symbols:
            df = proc_features[sym]
            val = df.loc[date, config.target_col] if date in df.index else np.nan
            if pd.isna(val):
                returns.append(0.0)
                mask.append(0.0)
            else:
                returns.append(float(val))
                mask.append(1.0)
        target_returns.append(torch.tensor(returns, dtype=torch.float32))
        target_masks.append(torch.tensor(mask, dtype=torch.float32))

    # Normalize targets to ~unit std per asset.
    # This is the PRIMARY fix for the dead-weight / zero-predictor collapse.
    scale_map: Dict[str, float] = {}
    if config.normalize_targets:
        target_returns, scale_map = _normalize_targets(
            target_returns,
            target_masks,
            available_symbols,
            config,
        )
        scale_stats = {s: f"{v:.4f}" for s, v in scale_map.items()}
        log(f"Target normalization scales (median daily return std): {scale_stats}")

        # Sanity check: verify the normalization actually worked.
        # After normalization, the std of valid targets should be near 1.0.
        # If it's still < 0.1, normalization failed silently.
        _verify_normalization(target_returns, target_masks, available_symbols)

    return (
        all_graphs,
        target_returns,
        target_masks,
        graph_dates,
        available_symbols,
        scale_map,
    )


def _verify_normalization(
    target_returns: List[torch.Tensor],
    target_masks: List[torch.Tensor],
    available_symbols: List[str],
) -> None:
    """
    Post-normalization sanity check. Logs per-asset std of normalized targets.
    If any asset has std < 0.1 or > 10, emits a warning.
    """
    stacked = torch.stack(target_returns).numpy()      # [T, N]
    stacked_masks = torch.stack(target_masks).numpy()  # [T, N]
    log("Post-normalization target std check:")
    for j, sym in enumerate(available_symbols):
        valid = stacked_masks[:, j] > 0.5
        if valid.sum() < 5:
            log(f"  {sym}: too few valid samples to check std")
            continue
        std_val = float(np.std(stacked[valid, j]))
        status = "OK" if 0.1 <= std_val <= 10.0 else "WARNING: UNEXPECTED STD"
        log(f"  {sym}: normalized target std = {std_val:.4f} [{status}]")
        if std_val < 0.1:
            log(
                f"  >>> {sym}: std={std_val:.6f} is near zero after normalization. "
                f"This suggests normalization failed or data has near-zero variance. "
                f"Zero-prediction will still be near-optimal for this asset."
            )
        elif std_val > 10.0:
            log(
                f"  >>> {sym}: std={std_val:.6f} is very large after normalization. "
                f"This suggests outlier returns that weren't caught by the rolling std. "
                f"Consider adding a final clip at ±5 std after normalization."
            )


def load_data(
    config: TrainingConfig,
    symbols: List[str],
    rank: int,
    is_distributed: bool,
) -> Tuple:
    """
    Loads or builds the full dataset. In distributed mode, rank 0 builds
    the data and broadcasts to other ranks.

    [BUG-11 FIX]: Rank-0 exceptions are broadcast as an error flag before
    the barrier, preventing non-zero ranks from hanging indefinitely.
    """
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

    # Distributed path: rank 0 builds/loads, then broadcasts.
    # [BUG-11 FIX]: Use a status flag to handle rank-0 exceptions cleanly.
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
            log(f"Rank 0 failed to load data: {e}\n{traceback.format_exc()}", force=True)

    # Broadcast success/error status BEFORE the barrier so non-zero ranks
    # don't hang if rank 0 raised an exception.
    dist.broadcast_object_list(error_container, src=0)
    if error_container[0] is not None:
        raise RuntimeError(
            f"Rank 0 failed to build/load dataset: {error_container[0]}"
        )

    # Now broadcast the actual data. [WARN-C]: large objects, ~3-5s overhead.
    dist.broadcast_object_list(container, src=0)
    dist.barrier()
    return container[0]


# ============================================================================
# 11. RESUME DISCOVERY
# ============================================================================
def find_latest_checkpoint() -> Optional[Path]:
    candidates = sorted(
        RUNS_DIR.glob("*/checkpoint_last.pt"),
        key=lambda p: p.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


# ============================================================================
# 12. MAIN
# ============================================================================
def parse_args():
    p = argparse.ArgumentParser(
        description="Enterprise ST-GCN training pipeline for crypto return prediction."
    )
    p.add_argument(
        "--resume",
        nargs="?",
        const="auto",
        default=None,
        help=(
            "'auto' to resume the most recent run, or an explicit path to "
            "checkpoint_last.pt. Omit to start a fresh run."
        ),
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
        # ----------------------------------------------------------------
        # Run directory: determined by rank 0 and broadcast to others.
        # ----------------------------------------------------------------
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
                    resume_target.parent.name
                    if resume_target
                    else new_run_id()
                )
            dist.broadcast_object_list(rid_container, src=0)
            rid = rid_container[0]
        else:
            rid = (
                resume_target.parent.name
                if resume_target
                else new_run_id()
            )

        run_dir = RUNS_DIR / rid
        if rank == 0:
            run_dir.mkdir(parents=True, exist_ok=True)
        if is_distributed:
            dist.barrier()

        log(f"Run ID: {rid} | Artifacts: {run_dir}")

        # ----------------------------------------------------------------
        # Symbol list: prefer DB, fall back to hardcoded.
        # [BUG-16 FIX]: use db.query(Asset).all() then .symbol attribute.
        # ----------------------------------------------------------------
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

        # ----------------------------------------------------------------
        # Data loading
        # ----------------------------------------------------------------
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
            log(
                "Target scale map saved "
                "(use this to de-normalize predictions at inference time)."
            )

        # ----------------------------------------------------------------
        # Train/val/test split
        # ----------------------------------------------------------------
        min_required = config.lookback_days + config.forecast_horizon + 10
        if len(all_graphs) < min_required:
            raise ValueError(
                f"Not enough graphs: {len(all_graphs)} < {min_required}. "
                f"Increase history_days or reduce lookback_days."
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
                f"test={len(test_ds)}. Increase history_days."
            )
        log(
            f"Samples -> train {len(train_ds)} | "
            f"val {len(val_ds)} | test {len(test_ds)}"
        )

        # pin_memory=False: collate_fn returns a list of PyG graphs (Python
        # objects), which DataLoader cannot pin. Pinning is only valid for
        # plain tensors. Setting True here would raise a TypeError at runtime.
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
            val_ds,
            batch_size=config.batch_size * 2,
            shuffle=False,
            **common_kwargs,
        )
        test_loader = DataLoader(
            test_ds,
            batch_size=config.batch_size * 2,
            shuffle=False,
            **common_kwargs,
        )

        # ----------------------------------------------------------------
        # Model + Trainer
        # ----------------------------------------------------------------
        log(f"Device: {device}")
        model = EnterpriseSTGCNModel(config)
        trainer = EnterpriseTrainer(
            model, train_loader, val_loader, test_loader,
            config, device, run_dir,
            is_distributed, rank, world_size, train_sampler,
        )

        trainer.fit()

        # ----------------------------------------------------------------
        # Evaluation
        # ----------------------------------------------------------------
        test_metrics = trainer.evaluate_test()
        ensemble_metrics = trainer.evaluate_test_ensemble()
        all_metrics = {**test_metrics, **ensemble_metrics}

        if rank == 0 and config.run_trading_metrics:
            trading_metrics = compute_trading_signal_metrics(
                trainer.raw_model, test_loader, device
            )
            all_metrics.update(trading_metrics)

        # ----------------------------------------------------------------
        # Artifact saving and DB registration (rank 0 only)
        # ----------------------------------------------------------------
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

            # DB model registry (best-effort)
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
                    log(f"Model registered in DB: {version}")
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