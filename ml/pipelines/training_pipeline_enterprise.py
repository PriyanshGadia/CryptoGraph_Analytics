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
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

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

current = Path(__file__).resolve()
workspace_root = current
for _parent in current.parents:
    if ((_parent / ".git").exists() or (_parent / "README.md").exists() or (_parent / "ARCHITECTURE.md").exists()):
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
    return False, 0, 0, 1, torch.device("cuda" if torch.cuda.is_available() else "cpu")

def cleanup_distributed(is_distributed: bool):
    if is_distributed:
        try:
            dist.destroy_process_group()
        except Exception:
            pass

@dataclass
class TrainingConfig:
    lookback_days: int = 30
    forecast_horizon: int = 1
    feature_dim: int = 24
    target_col: str = "returns_1d"
    history_days: int = 3650
    max_missing_frac: float = 0.95
    use_cache: bool = True
    cache_max_age_hours: float = 24.0

    hidden_dim: int = 64
    gat_heads_1: int = 2
    gat_heads_2: int = 2
    transformer_layers: int = 2
    transformer_heads: int = 4
    dropout: float = 0.40
    use_tcn: bool = True

    batch_size: int = 16
    max_epochs: int = 300
    learning_rate: float = 1e-4
    weight_decay: float = 5e-2
    warmup_epochs: int = 10
    grad_clip: float = 1.0
    early_stopping_patience: int = 45

    log_var_min: float = -3.0
    log_var_max: float = 4.0
    entropy_beta: float = 0.30

    normalize_targets: bool = True
    target_norm_window: int = 60

    ensemble_size: int = 5
    mc_dropout_samples: int = 30

    use_sam: bool = True
    sam_rho: float = 0.05
    aux_mse_weight: float = 0.5
    min_pred_std_warn: float = 0.05
    use_amp: bool = True
    num_workers: int = 0
    max_train_hours: float = 8.5
    checkpoint_every_epochs: int = 1
    seed: int = 42
    cudnn_benchmark: bool = False

    run_permutation_importance: bool = True
    importance_max_batches: int = 15
    run_trading_metrics: bool = True

    corr_threshold: float = 0.6
    mc_threshold: float = 0.3
    rank_loss_weight: float = 0.1
    label_smooth_alpha: float = 0.0
    confidence_gate_threshold: float = 1.5
    directional_loss_weight: float = 0.30
    topk_pct: float = 0.25
    pin_memory: bool = False
    spread_gate_threshold: float = 0.15

    def to_dict(self) -> dict:
        return asdict(self)

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

def graph_collate_fn(batch):
    from torch_geometric.data import Batch
    sequences = [item[0] for item in batch]
    flat_graphs = []
    for seq in sequences:
        flat_graphs.extend(seq)
    batched_graphs = Batch.from_data_list(flat_graphs)
    targets = torch.stack([item[1] for item in batch], dim=0)
    masks = torch.stack([item[2] for item in batch], dim=0)
    return batched_graphs, targets, masks

class WindowedGraphDataset(Dataset):
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
                dilations=[1, 2, 4, 8],
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
        self.train()
        for m in self.modules():
            if isinstance(m, (nn.BatchNorm1d, nn.BatchNorm2d, nn.BatchNorm3d)):
                m.eval()

    def disable_mc_dropout(self):
        self.eval()

    def forward(
        self,
        batch_sequences: Any,
        return_uncertainty: bool = False,
    ):
        from torch_geometric.data import Batch

        if isinstance(batch_sequences, Batch):
            batched = batch_sequences
            T = self.config.lookback_days
            B = batched.num_graphs // T
            N_nodes = batched.num_nodes // batched.num_graphs
        else:
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

            flat = []
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

        batched = batched.clone()
        x = F.relu(self.projection(batched.x))
        x = self.proj_norm(x)
        batched.x = x

        x = self.spatial_gat(batched, T=T, B=B)
        x = self.temporal_encoder(x)

        if x.dim() != 2 or x.shape[0] != B * N_nodes:
            raise ValueError(
                f"temporal_encoder output shape {tuple(x.shape)} unexpected; "
                f"expected [{B * N_nodes}, hidden_dim]."
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
        checkpoint = torch.load(path, map_location=map_location, weights_only=False)
        config = TrainingConfig()
        for k, v in checkpoint["config"].items():
            if hasattr(config, k):
                setattr(config, k, v)
        model = cls(config)
        model.load_state_dict(checkpoint["model_state_dict"])
        return model

class EnterpriseTrainer:
    def __init__(
        self,
        model: nn.Module,
        train_loader: DataLoader,
        val_loader: DataLoader,
        test_loader: DataLoader,
        config: TrainingConfig,
        device: torch.device,
        run_dir: Path,
        is_distributed: bool = False,
        rank: int = 0,
        world_size: int = 1,
        train_sampler: Optional[DistributedSampler] = None,
    ):
        self.model = model.to(device)
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.test_loader = test_loader
        self.config = config
        self.device = device
        self.run_dir = run_dir
        self.is_distributed = is_distributed
        self.rank = rank
        self.world_size = world_size
        self.train_sampler = train_sampler

        if is_distributed:
            self.model = DDP(
                self.model,
                device_ids=[device.index] if device.type == "cuda" else None,
                output_device=device.index if device.type == "cuda" else None,
                find_unused_parameters=True,
            )

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

    def _compute_cosine_alignment_loss(
        self,
        pred: torch.Tensor,
        target: torch.Tensor,
        mask: torch.Tensor,
    ) -> torch.Tensor:
        device = pred.device
        B = pred.shape[0]
        cos_sims = []
        for b in range(B):
            valid = mask[b].bool()
            if valid.sum() < 2:
                continue
            p = pred[b][valid]
            t = target[b][valid]
            p_norm = p.norm()
            t_norm = t.norm()
            if p_norm > 1e-8 and t_norm > 1e-8:
                sim = (p * t).sum() / (p_norm * t_norm)
                cos_sims.append(sim)
        if cos_sims:
            return 1.0 - torch.stack(cos_sims).mean()
        return torch.tensor(0.0, device=device, requires_grad=True)

    def _compute_loss(
        self,
        pred: torch.Tensor,
        target: torch.Tensor,
        log_var: torch.Tensor,
        mask: torch.Tensor,
    ) -> torch.Tensor:
        if self.config.label_smooth_alpha > 0.0:
            alpha = self.config.label_smooth_alpha
            target = target * (1.0 - alpha) + torch.sign(target) * alpha

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
            if self.config.aux_mse_weight > 0.0:
                mse_aux = self.config.aux_mse_weight * F.mse_loss(
                    pred[valid_mask], target[valid_mask]
                )
            else:
                mse_aux = torch.tensor(0.0, device=pred.device)
        else:
            entropy_reg = torch.tensor(0.0, device=pred.device)
            mse_aux = torch.tensor(0.0, device=pred.device)

        total = nll_loss + entropy_reg + mse_aux

        if self.config.rank_loss_weight > 0.0 and pred.dim() == 2:
            cos_loss = self._compute_cosine_alignment_loss(pred, target, mask)
            total = total + self.config.rank_loss_weight * cos_loss

        if self.config.directional_loss_weight > 0.0 and valid_mask.any():
            sign_target = (target[valid_mask] > 0).float()
            sign_target = sign_target * 0.9 + 0.05
            
            pred_valid = pred[valid_mask]
            pred_std = pred_valid.std()
            if pred_std > 1e-6:
                logits = pred_valid / pred_std
            else:
                logits = pred_valid
                
            dir_loss = F.binary_cross_entropy_with_logits(
                logits, sign_target, reduction="mean"
            )
            total = total + self.config.directional_loss_weight * dir_loss

        return total

    def _forward_backward(self, sequences, targets, masks) -> Tuple[float, float]:
        if isinstance(sequences, list):
            sequences_dev = [
                [g.to(self.device, non_blocking=True) for g in seq]
                for seq in sequences
            ]
        else:
            sequences_dev = sequences.to(self.device, non_blocking=True)
        targets_dev = targets.to(self.device, non_blocking=True)
        masks_dev = masks.to(self.device, non_blocking=True)

        amp_enabled = self.scaler is not None
        with torch.amp.autocast("cuda", enabled=amp_enabled):
            pred, log_var = self.model(sequences_dev, return_uncertainty=True)
            loss = self._compute_loss(pred, targets_dev, log_var, masks_dev)

        if not torch.isfinite(loss):
            p_tied = sum(p.sum() for p in self.model.parameters())
            loss = 0.0 * p_tied

        if self.scaler is not None:
            self.scaler.scale(loss).backward()
        else:
            loss.backward()

        valid_mask = masks_dev.bool()
        if valid_mask.any():
            mse_val = F.mse_loss(pred[valid_mask], targets_dev[valid_mask]).item()
        else:
            mse_val = 0.0

        return loss.item(), mse_val

    def _check_prediction_variance(self, loader: DataLoader, label: str):
        self.raw_model.eval()
        preds_collected = []
        log_vars_collected = []
        with torch.no_grad():
            for i, (sequences, targets, masks) in enumerate(loader):
                if i >= 5:
                    break
                if isinstance(sequences, list):
                    seq_dev = [[g.to(self.device) for g in seq] for seq in sequences]
                else:
                    seq_dev = sequences.to(self.device)
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
        if pred_std < self.config.min_pred_std_warn:
            log(
                f"WARNING: pred_std={pred_std:.4f} is below {self.config.min_pred_std_warn:.2f} "
                f"-- model is predicting near-constant values on unit-normalized targets. "
                f"[R4] This may indicate the NLL degenerate minimum (pred~0, log_var~0). "
                f"Check aux_mse_weight > 0 and that features are not all-zero constants."
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
        total_nll, total_combined, n_steps = 0.0, 0.0, 0
        all_preds, all_targets, all_vars = [], [], []

        for sequences, targets, masks in self.val_loader:
            if masks.sum() == 0:
                continue

            if isinstance(sequences, list):
                sequences_dev = [[g.to(self.device) for g in seq] for seq in sequences]
            else:
                sequences_dev = sequences.to(self.device)
            targets_dev = targets.to(self.device)
            masks_dev = masks.to(self.device)

            pred, log_var = self.raw_model(sequences_dev, return_uncertainty=True)
            combined_loss = self._compute_loss(pred, targets_dev, log_var, masks_dev)

            log_var_c = torch.clamp(log_var, min=self.config.log_var_min, max=self.config.log_var_max)
            precision = torch.exp(-log_var_c)
            per_node = 0.5 * precision * (pred - targets_dev) ** 2 + 0.5 * log_var_c
            denom = masks_dev.sum().clamp_min(1.0)
            nll = (per_node * masks_dev).sum() / denom
            valid_mask = masks_dev.bool()
            if valid_mask.any():
                nll = nll + self.config.entropy_beta * F.relu(-log_var_c[valid_mask]).mean()

            if torch.isfinite(combined_loss):
                total_nll += nll.item() if torch.isfinite(nll) else 0.0
                total_combined += combined_loss.item()
                n_steps += 1

            valid = masks.bool().numpy()
            all_preds.append(pred.cpu().numpy()[valid])
            all_targets.append(targets.numpy()[valid])
            var = torch.exp(
                torch.clamp(log_var, max=self.config.log_var_max)
            ).cpu().numpy()
            all_vars.append(var[valid])

            del pred, log_var, combined_loss, sequences_dev, targets_dev, masks_dev

        n_steps = max(n_steps, 1)
        preds = np.concatenate(all_preds) if all_preds else np.array([0.0])
        targets_np = np.concatenate(all_targets) if all_targets else np.array([0.0])
        variances = np.concatenate(all_vars) if all_vars else np.array([1.0])

        r2 = float(r2_score(targets_np, preds)) if len(preds) > 1 else 0.0
        return {
            "val_nll": total_nll / n_steps,
            "val_loss": total_combined / n_steps,
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
            val_rmse = self._sync_scalar(val_metrics.get("val_rmse", float("inf")))
            val_loss = val_rmse

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
                    shutil_target = Path("/kaggle/working") / "best_model.pt"
                    if shutil_target.parent.exists():
                        try:
                            import shutil
                            shutil.copy(str(ARTIFACTS_DIR / "best_model.pt"), str(shutil_target))
                            log(f"Copied best model to {shutil_target}")
                        except Exception as e:
                            log(f"Failed to copy to top-level working (non-fatal): {e}")
                    
                    root_shutil = workspace_root / "best_model.pt"
                    try:
                        import shutil
                        shutil.copy(str(ARTIFACTS_DIR / "best_model.pt"), str(root_shutil))
                        log(f"Copied best model to repo root: {root_shutil}")
                    except Exception as e:
                        log(f"Failed to copy to repo root (non-fatal): {e}")
            else:
                self.patience_counter += 1

            self._barrier()
            self._maybe_save_snapshot(val_rmse, epoch)
            self._save_full_checkpoint()

            if self.rank == 0:
                dt = time.time() - epoch_start
                log(
                    f"Epoch {epoch:03d} | Train loss: {train_metrics['train_loss']:.4f} | "
                    f"Val Loss: {val_loss:.4f} | RMSE: {val_metrics.get('val_rmse', 0.0):.4f} | "
                    f"R2: {val_metrics.get('val_r2', 0.0):.4f} | "
                    f"patience: {self.patience_counter}/{self.config.early_stopping_patience} | "
                    f"lr: {train_metrics['lr']:.2e} | time: {dt:.1f}s"
                )
                if epoch % 5 == 0 or improved:
                    self._check_prediction_variance(self.val_loader, "val")

            patience_triggered = self.patience_counter >= self.config.early_stopping_patience
            global_stop = self._sync_bool(patience_triggered)

            elapsed_hours = (time.time() - self.run_start_time) / 3600.0
            timeout_triggered = elapsed_hours >= self.config.max_train_hours
            global_timeout = self._sync_bool(timeout_triggered)

            if global_timeout and self.rank == 0:
                log(f"Training timed out after {elapsed_hours:.2f} hours; stopping.")

            if global_stop or global_timeout:
                break

        self._barrier()
        if self.rank == 0:
            self._finalize_snapshots()
            log("Training complete.")

    @torch.no_grad()
    def evaluate_test(self) -> Dict[str, float]:
        self.raw_model.eval()
        all_preds, all_targets, all_vars = [], [], []

        for sequences, targets, masks in self.test_loader:
            if masks.sum() == 0:
                continue
            if isinstance(sequences, list):
                seq_dev = [[g.to(self.device) for g in seq] for seq in sequences]
            else:
                seq_dev = sequences.to(self.device)
            pred, log_var = self.raw_model(seq_dev, return_uncertainty=True)

            valid = masks.bool().numpy()
            all_preds.append(pred.cpu().numpy()[valid])
            all_targets.append(targets.numpy()[valid])
            var = torch.exp(torch.clamp(log_var, max=self.config.log_var_max)).cpu().numpy()
            all_vars.append(var[valid])

        if not all_preds:
            return {}

        preds = np.concatenate(all_preds)
        targets_np = np.concatenate(all_targets)
        variances = np.concatenate(all_vars)

        rmse = float(np.sqrt(mean_squared_error(targets_np, preds)))
        mae = float(mean_absolute_error(targets_np, preds))
        r2 = float(r2_score(targets_np, preds)) if len(preds) > 1 else 0.0

        errors = preds - targets_np
        z_scores = errors / np.sqrt(np.clip(variances, 1e-12, None))
        coverage_95 = float(np.mean(np.abs(z_scores) <= 1.96))

        return {
            "test_rmse": rmse,
            "test_mae": mae,
            "test_r2": r2,
            "test_coverage_95": coverage_95,
            "test_mean_var": float(variances.mean()),
            "test_n_valid_targets": int(len(preds)),
        }

    @torch.no_grad()
    def evaluate_test_ensemble(self) -> Dict[str, float]:
        self.raw_model.eval()
        ranked = sorted(self.snapshot_heap, key=lambda e: -e[0])
        models = []
        for entry in ranked:
            path = entry[2]
            try:
                models.append(EnterpriseSTGCNModel.load(path, map_location=str(self.device)))
            except Exception as e:
                log(f"Failed to load snapshot {path} for ensembling: {e}")

        if not models:
            log("No snapshots found for ensembling; returning standard test metrics.")
            return {}

        for m in models:
            m.eval()

        all_preds, all_targets, all_vars = [], [], []

        for sequences, targets, masks in self.test_loader:
            if masks.sum() == 0:
                continue
            if isinstance(sequences, list):
                seq_dev = [[g.to(self.device) for g in seq] for seq in sequences]
            else:
                seq_dev = sequences.to(self.device)

            batch_preds = []
            batch_vars = []
            for m in models:
                pred, log_var = m(seq_dev, return_uncertainty=True)
                batch_preds.append(pred.cpu().numpy())
                var = torch.exp(torch.clamp(log_var, max=self.config.log_var_max)).cpu().numpy()
                batch_vars.append(var)

            avg_pred = np.mean(batch_preds, axis=0)
            avg_var = np.mean(batch_vars, axis=0) + np.var(batch_preds, axis=0)

            valid = masks.bool().numpy()
            all_preds.append(avg_pred[valid])
            all_targets.append(targets.numpy()[valid])
            all_vars.append(avg_var[valid])

        if not all_preds:
            return {}

        preds = np.concatenate(all_preds)
        targets_np = np.concatenate(all_targets)
        variances = np.concatenate(all_vars)

        rmse = float(np.sqrt(mean_squared_error(targets_np, preds)))
        mae = float(mean_absolute_error(targets_np, preds))
        r2 = float(r2_score(targets_np, preds)) if len(preds) > 1 else 0.0

        errors = preds - targets_np
        z_scores = errors / np.sqrt(np.clip(variances, 1e-12, None))
        coverage_95 = float(np.mean(np.abs(z_scores) <= 1.96))

        return {
            "ensemble_test_rmse": rmse,
            "ensemble_test_mae": mae,
            "ensemble_test_r2": r2,
            "ensemble_test_coverage_95": coverage_95,
            "ensemble_test_mean_var": float(variances.mean()),
            "ensemble_test_n_valid_targets": int(len(preds)),
        }

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
            from torch_geometric.data import Batch
            if isinstance(sequences, Batch):
                flat_list = sequences.to_data_list()
                T = model.config.lookback_days
                B = len(flat_list) // T
                sequences_list = [flat_list[b * T : (b + 1) * T] for b in range(B)]
            else:
                sequences_list = sequences

            seq_dev = []
            for seq in sequences_list:
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

@torch.no_grad()
def compute_trading_signal_metrics(
    model: EnterpriseSTGCNModel,
    test_loader: DataLoader,
    device: torch.device,
    scale_map: Optional[Dict[str, float]] = None,
    available_symbols: Optional[List[str]] = None,
    confidence_gate_threshold: float = 1.5,
) -> Dict[str, float]:
    try:
        from ml.evaluation.finance_metrics import compute_all_finance_metrics
    except Exception as e:
        log(f"compute_all_finance_metrics unavailable ({e}); skipping.")
        return {}

    model.eval()
    N = len(available_symbols) if available_symbols else None

    if scale_map and available_symbols:
        scales = torch.tensor(
            [scale_map.get(sym, 1.0) for sym in available_symbols],
            dtype=torch.float32,
        )
    else:
        scales = None

    daily_returns = []
    daily_returns_raw = []
    spread_gated_returns = []
    pred_stds = []
    topk_pct = getattr(model.config, "topk_pct", 0.25)
    spread_gate_thresh = getattr(model.config, "spread_gate_threshold", 0.15)

    for sequences, targets, masks in test_loader:
        from torch_geometric.data import Batch
        if isinstance(sequences, Batch):
            flat_list = sequences.to_data_list()
            T = model.config.lookback_days
            B = len(flat_list) // T
            sequences_list = [flat_list[b * T : (b + 1) * T] for b in range(B)]
        else:
            sequences_list = sequences

        for b in range(len(sequences_list)):
            mask_b = masks[b]
            if mask_b.sum() == 0:
                continue
            seq_dev = [[g.to(device) for g in sequences_list[b]]]
            pred_raw, log_var_raw = model(seq_dev, return_uncertainty=True)
            pred = pred_raw.cpu()[0]
            log_var = log_var_raw.cpu()[0]
            pred_std_day = float(torch.exp(0.5 * log_var.clamp(max=4.0))[mask_b.bool()].mean().item())
            valid = mask_b.bool()
            if valid.sum() == 0:
                continue

            targets_b = targets[b]
            if scales is not None and len(scales) == len(targets_b):
                raw_targets = targets_b * scales
            else:
                raw_targets = targets_b

            valid_pred = pred[valid]
            valid_ret  = raw_targets[valid]
            n_valid = int(valid.sum().item())
            k = max(1, int(round(n_valid * topk_pct)))

            if n_valid >= 2:
                sorted_idx = torch.argsort(valid_pred)
                long_idx  = sorted_idx[-k:]
                short_idx = sorted_idx[:k]

                long_ret  = valid_ret[long_idx].mean().item()
                short_ret = valid_ret[short_idx].mean().item()
                ls_ret = 0.5 * (long_ret - short_ret)
                daily_returns.append(ls_ret)

                pred_spread = valid_pred[long_idx].mean().item() - valid_pred[short_idx].mean().item()
                if pred_spread >= spread_gate_thresh:
                    spread_gated_returns.append(ls_ret)

                signal_all = torch.sign(valid_pred)
                daily_returns_raw.append((signal_all * valid_ret).mean().item())
            else:
                signal_all = torch.sign(valid_pred)
                day_ret = (signal_all * valid_ret).mean().item()
                daily_returns.append(day_ret)
                daily_returns_raw.append(day_ret)
                if abs(valid_pred.item()) >= spread_gate_thresh:
                    spread_gated_returns.append(day_ret)

            pred_stds.append(pred_std_day)

    if len(daily_returns) < 2:
        log("Not enough valid days for trading metrics.")
        return {}

    try:
        fin = compute_all_finance_metrics(pd.Series(daily_returns))
        fin = {f"strategy_{k}": float(v) for k, v in fin.items()}

        if len(daily_returns_raw) >= 2:
            raw_fin = compute_all_finance_metrics(pd.Series(daily_returns_raw))
            fin.update({f"raw_strategy_{k}": float(v) for k, v in raw_fin.items()})
            log(
                f"[strategy:raw sign-all] "
                f"sharpe={raw_fin.get('sharpe_ratio', 0):.3f} | "
                f"win_rate={raw_fin.get('win_rate', 0):.3f}"
            )

        if len(spread_gated_returns) >= 2:
            spread_fin = compute_all_finance_metrics(pd.Series(spread_gated_returns))
            fin.update({f"spread_gated_strategy_{k}": float(v) for k, v in spread_fin.items()})
            fin["spread_gated_coverage"] = float(len(spread_gated_returns) / len(daily_returns))
            log(f"[strategy:spread-gated L/S] coverage={fin['spread_gated_coverage']:.1%} | {spread_fin}")

        gated_returns = [dr for dr, pg in zip(daily_returns, pred_stds)
                         if pg <= confidence_gate_threshold]
        gated_coverage = len(gated_returns) / max(len(daily_returns), 1)
        if len(gated_returns) >= 2:
            gated_fin = compute_all_finance_metrics(pd.Series(gated_returns))
            fin.update({f"gated_strategy_{k}": float(v) for k, v in gated_fin.items()})
            fin["gated_coverage"] = float(gated_coverage)
            log(f"[strategy:gated L/S] coverage={gated_coverage:.1%} | {gated_fin}")

        log(f"[strategy:L/S market-neutral] {fin}")
        return fin
    except Exception as e:
        log(f"compute_all_finance_metrics failed ({e}); skipping.")
        return {}

def _extract_targets_safe(
    proc_features: Dict[str, pd.DataFrame],
    graph_dates: List[datetime],
    available_symbols: List[str],
    target_col: str,
) -> Tuple[List[torch.Tensor], List[torch.Tensor]]:
    pd_dates = [pd.Timestamp(d).tz_localize("UTC") if d.tzinfo is None
                else pd.Timestamp(d).tz_convert("UTC")
                for d in graph_dates]

    T = len(pd_dates)
    N = len(available_symbols)

    values_arr = np.full((T, N), np.nan, dtype=np.float64)
    for j, sym in enumerate(available_symbols):
        df = proc_features[sym]
        col_series = df[target_col].clip(lower=-0.5, upper=0.5).reindex(pd_dates)
        values_arr[:, j] = col_series.values

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

    stacked_vals = np.array([[r.item() for r in row] for row in target_returns])
    stacked_masks_np = np.array([[m.item() for m in row] for row in target_masks])

    n_total = T * N
    n_valid = int(stacked_masks_np.sum())
    mask_rate = n_valid / max(n_total, 1)

    log(
        f"Target extraction: {n_valid}/{n_total} valid ({mask_rate:.1%})."
    )

    if mask_rate < 0.5:
        raise RuntimeError(
            f"CRITICAL: Target extraction produced only {mask_rate:.1%} valid targets."
        )

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

def _normalize_targets(
    raw_targets: List[torch.Tensor],
    masks: List[torch.Tensor],
    available_symbols: List[str],
    config: "TrainingConfig",
) -> Tuple[List[torch.Tensor], Dict[str, float]]:
    W = config.target_norm_window
    N = len(available_symbols)
    T = len(raw_targets)

    if T == 0 or N == 0:
        return raw_targets, {}

    stacked = torch.stack(raw_targets).numpy()
    stacked_masks = torch.stack(masks).numpy()

    scale_map: Dict[str, float] = {}
    per_sample_scales = np.ones((T, N), dtype=np.float64)

    for j, sym in enumerate(available_symbols):
        series = stacked[:, j].copy().astype(np.float64)
        mask_j = stacked_masks[:, j]
        series[mask_j < 0.5] = np.nan
        s = pd.Series(series)
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
                f"Using global std={median_std:.5f} as fallback."
            )
        scale_map[sym] = median_std

        last_valid_std = median_std
        filled_stds = np.empty(T, dtype=np.float64)
        for t in range(T):
            s_t = rolling_std[t]
            if not np.isnan(s_t) and s_t > 1e-6:
                last_valid_std = float(s_t)
            filled_stds[t] = last_valid_std

        per_sample_scales[:, j] = filled_stds

    normalized: List[torch.Tensor] = []
    for t in range(T):
        row = raw_targets[t] / torch.tensor(per_sample_scales[t], dtype=torch.float32)
        normalized.append(row)

    return normalized, scale_map

def _verify_normalization(
    targets: List[torch.Tensor],
    masks: List[torch.Tensor],
    available_symbols: List[str],
):
    stacked = torch.stack(targets).numpy()
    stacked_masks = torch.stack(masks).numpy()
    any_failed = False
    log("Post-normalization target std check:")
    for j, sym in enumerate(available_symbols):
        mask_j = stacked_masks[:, j] > 0.5
        if not mask_j.any():
            log(f"  {sym}: no valid targets")
            continue
        vals = stacked[mask_j, j]
        std_val = float(vals.std())
        mean_val = float(vals.mean())
        if 0.1 <= std_val <= 3.0:
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
            "Target normalization produced near-zero std for one or more assets."
        )

_CACHE_VERSION = "r13"

def _cache_key(symbols: List[str], config: TrainingConfig) -> str:
    payload = json.dumps(
        {
            "cache_version": _CACHE_VERSION,
            "symbols": sorted(symbols),
            "history_days": config.history_days,
            "feature_dim": config.feature_dim,
            "target_col": config.target_col,
            "max_missing_frac": config.max_missing_frac,
            "normalize_targets": config.normalize_targets,
            "target_norm_window": config.target_norm_window,
            "corr_threshold": config.corr_threshold,
            "mc_threshold": config.mc_threshold,
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
    date_sets: Dict[str, set] = {}
    for s in symbols:
        date_sets[s] = set(proc_features[s].index)

    surviving = []
    current_ts = pd.Timestamp(start_dt).tz_convert("UTC")
    end_ts = pd.Timestamp(end_dt).tz_convert("UTC")
    one_day = pd.Timedelta(days=1)
    n_symbols = len(symbols)

    while current_ts <= end_ts:
        missing = sum(1 for s in symbols if current_ts not in date_sets[s])
        if missing / n_symbols <= max_missing_frac:
            surviving.append(current_ts.to_pydatetime())
        current_ts += one_day

    return surviving

def _log_feature_coverage(
    proc_features: Dict[str, pd.DataFrame],
    available_symbols: List[str],
) -> None:
    if not available_symbols or not proc_features:
        return

    first_df = proc_features[available_symbols[0]]
    feature_cols = [c for c in first_df.columns if c not in {"timestamp", "returns_1d"}]
    if not feature_cols:
        return

    dead_features = []
    near_constant_features = []
    log("Feature coverage diagnostic (constant detection):")
    for col in feature_cols:
        stds = []
        for sym in available_symbols:
            df = proc_features[sym]
            if col in df.columns:
                stds.append(float(df[col].std()))
        if not stds:
            continue
        max_std = max(stds)
        if max_std < 1e-8:
            dead_features.append(col)
        elif max_std < 1e-3:
            near_constant_features.append(col)

    n_total = len(feature_cols)
    n_dead = len(dead_features)
    n_near = len(near_constant_features)

    if n_dead > 0:
        log(
            f"  DEAD features ({n_dead}/{n_total}, std<1e-8 across all assets): {dead_features}"
        )
    if n_near > 0:
        log(
            f"  NEAR-CONSTANT features ({n_near}/{n_total}, std<1e-3): {near_constant_features}"
        )
    if n_dead + n_near == 0:
        log(f"  All {n_total} features have reasonable variance. [OK]")

    dead_frac = n_dead / max(n_total, 1)
    if dead_frac >= 0.20:
        log(
            f"  WARNING [{dead_frac:.0%} dead features]: Model has high dead feature ratios."
        )

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
        corr_threshold=config.corr_threshold,
        mc_threshold=config.mc_threshold,
    )

    proc_features: Dict[str, pd.DataFrame] = {}
    for sym in available_symbols:
        df = features[sym].copy()
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        df.index = (
            df.index.tz_localize("UTC")
            if df.index.tz is None
            else df.index.tz_convert("UTC")
        )
        df.index = df.index.floor("D")
        df = df[~df.index.duplicated(keep="last")]
        if config.target_col not in df.columns:
            raise ValueError(
                f"target_col='{config.target_col}' not found for {sym}."
            )
        proc_features[sym] = df

    _log_feature_coverage(proc_features, available_symbols)

    first_df = proc_features[available_symbols[0]]
    log(
        f"proc_features index sample: type={type(first_df.index[0]).__name__}, "
        f"value={first_df.index[0]}, tz={first_df.index.tz}"
    )

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    surviving_dates = _determine_surviving_dates(
        proc_features, available_symbols, start_dt, end_dt, config.max_missing_frac
    )
    log(
        f"Surviving dates: {len(surviving_dates)} "
        f"(first={surviving_dates[0].strftime('%Y-%m-%d')}, "
        f"last={surviving_dates[-1].strftime('%Y-%m-%d')})"
    )

    all_graphs = []
    for d in surviving_dates:
        g = builder.build_graph(d, proc_features)
        all_graphs.append(g)
    log(f"Built {len(all_graphs)} daily graphs.")

    log("Extracting targets (timezone-safe)...")
    target_returns, target_masks = _extract_targets_safe(
        proc_features, surviving_dates, available_symbols, config.target_col
    )

    scale_map: Dict[str, float] = {}
    if config.normalize_targets:
        log("Computing normalization scales:")
        target_returns, scale_map = _normalize_targets(
            target_returns, target_masks, available_symbols, config
        )
        log(f"Target normalization scales (median daily return std): {scale_map}")

        _verify_normalization(target_returns, target_masks, available_symbols)

    return (
        all_graphs,
        target_returns,
        target_masks,
        surviving_dates,
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

    dist.broadcast_object_list(error_container, src=0)
    if error_container[0] is not None:
        raise RuntimeError(f"Rank 0 failed to build/load dataset: {error_container[0]}")

    dist.broadcast_object_list(container, src=0)
    dist.barrier()
    return container[0]

def find_latest_checkpoint() -> Optional[Path]:
    candidates = sorted(
        RUNS_DIR.glob("*/checkpoint_last.pt"),
        key=lambda p: p.stat().st_mtime,
    )
    return candidates[-1] if candidates else None

def parse_args():
    p = argparse.ArgumentParser(description="Enterprise ST-GCN training pipeline.")
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

    is_kaggle = os.environ.get("KAGGLE_KERNEL_RUN_TYPE") is not None or os.environ.get("KAGGLE_URL_BASE") is not None
    if is_kaggle:
        log("Detected KAGGLE environment. Running in HIGH PERFORMANCE mode.")
        
        # [R8-OPTIMIZATION] Prevent overfitting and speed up training
        config.hidden_dim = 32
        config.lookback_days = 14
        config.batch_size = 16
        config.corr_threshold = 0.85
        config.mc_threshold = 0.8
        config.max_epochs = 300
        config.ensemble_size = 5
        config.mc_dropout_samples = 30
        
        # Regularization & Learning Rate to combat validation deterioration
        config.dropout = 0.50
        config.weight_decay = 0.1
        config.learning_rate = 5e-5
        config.early_stopping_patience = 60
        
        # [R8-SPEED] Set num_workers=0 on Kaggle to bypass PyG CPU-GPU serialization overheads
        config.num_workers = 0
        config.pin_memory = True
        config.cudnn_benchmark = True
        config.use_sam = False
        config.history_days = 3650
    else:
        log("Detected LOCAL environment. Running in i3 OPTIMIZED LOW-RESOURCE mode.")
        config.hidden_dim = 32
        config.batch_size = 8
        config.max_epochs = 20
        config.ensemble_size = 1
        config.mc_dropout_samples = 5
        config.num_workers = 0
        config.use_sam = False
        config.run_permutation_importance = False
        config.early_stopping_patience = 5
        config.history_days = 365
        config.use_amp = False
        config.corr_threshold = 0.6
        config.mc_threshold = 0.3

    set_seed(config.seed)

    is_distributed, rank, local_rank, world_size, device = setup_distributed()
    _CURRENT_RANK = rank

    torch.backends.cudnn.benchmark = config.cudnn_benchmark
    if hasattr(torch.backends.cuda, "matmul"):
        torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    try:
        resume_target = None
        if args.resume == "auto":
            resume_target = find_latest_checkpoint()
            if resume_target is None and rank == 0:
                log("--resume auto: no existing checkpoint found; starting fresh.")
        elif args.resume:
            resume_target = Path(args.resume)
            if not resume_target.exists():
                raise FileNotFoundError(f"--resume path does not exist: {resume_target}")

        if is_distributed:
            rid_container = [None]
            if rank == 0:
                rid_container[0] = resume_target.parent.name if resume_target else new_run_id()
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
            from app.db.database import SessionLocal
            from app.db.models import Asset

            db = SessionLocal()
            symbols = [a.symbol for a in db.query(Asset).all()]
            db.close()
            if not symbols:
                raise ValueError("DB returned empty symbol list")
        except Exception as e:
            log(f"DB symbol lookup failed ({e}); using fallback symbol list.")
            symbols = [
                # Institutional Large Cap Utility & Layer-1 Chains (No noisy micro-caps/memes)
                "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "LTC", "BCH", "LINK",
                "AVAX", "DOT", "MATIC", "NEAR", "SUI", "APT", "ICP", "STX", "FTM", "ATOM",
                "UNI", "AAVE", "LDO", "MKR", "GRT"
            ]
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
            raise ValueError(f"Not enough graphs: {len(all_graphs)} < {min_required}.")

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
            raise ValueError("Empty split(s) in datasets setup.")
        log(
            f"Samples -> train {len(train_ds)} | "
            f"val {len(val_ds)} | test {len(test_ds)}"
        )

        common_kwargs = dict(
            collate_fn=graph_collate_fn,
            num_workers=config.num_workers,
            pin_memory=config.pin_memory,
            persistent_workers=(config.num_workers > 0),
            prefetch_factor=(2 if config.num_workers > 0 else None),
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

        cleanup_distributed(is_distributed)
        is_distributed = False

        all_metrics = {}
        if rank == 0:
            test_metrics = trainer.evaluate_test()
            ensemble_metrics = trainer.evaluate_test_ensemble()
            all_metrics = {**test_metrics, **ensemble_metrics}

            if config.run_trading_metrics:
                trading_metrics = compute_trading_signal_metrics(
                    trainer.raw_model, test_loader, device,
                    scale_map=scale_map,
                    available_symbols=available_symbols,
                    confidence_gate_threshold=config.confidence_gate_threshold,
                )
                all_metrics.update(trading_metrics)

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
                    log(f"Failed to compute permutation feature importance: {e}")

            try:
                from app.db.database import SessionLocal, Base, engine
                from app.db.models import ModelRegistry

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