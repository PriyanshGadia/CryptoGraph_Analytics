import torch
import numpy as np
from typing import List, Dict, Tuple, Optional
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR, LinearLR, SequentialLR
from torch.nn.utils import clip_grad_norm_

from ml.training.loss_v2 import MultiTaskFocalLoss
from ml.training.callbacks import EarlyStopping, ModelCheckpoint
from ml.experiments.wandb_tracker import WandbTracker
from ml.training.metrics import compute_all_metrics
from ml.models.stgcn import STGCNModel
from ml.training.sam import SAM

class STGCNTrainer:
    """Full training loop for the ST-GCN model with Focal Loss, Causal TCN / Transformer,
    warmup scheduling, gradient accumulation, optional SAM (Sharpness-Aware Minimization)
    flat-minima optimizer, and optional FGM (Fast Gradient Method) adversarial feature training.
    """

    def __init__(
        self,
        model: STGCNModel,
        train_graphs: List[Tuple], # list of (graph_sequence, dir_labels, vol_labels, returns, vol_raw)
        val_graphs: List[Tuple],   # same format
        config: dict
    ):
        self.model = model
        self.train_graphs = train_graphs
        self.val_graphs = val_graphs
        self.config = config
        
        self.device = next(model.parameters()).device
        
        self.use_sam = config.get("use_sam", False)
        self.use_fgm = config.get("use_fgm", True)
        self.fgm_epsilon = config.get("fgm_epsilon", 0.05)
        
        lr = config.get("learning_rate", config.get("lr", 1e-3))
        wd = config.get("weight_decay", 1e-4)
        
        # Instantiate optimizer (wrapped in SAM if configured)
        if self.use_sam:
            rho = config.get("sam_rho", 0.05)
            self.optimizer = SAM(model.parameters(), AdamW, rho=rho, lr=lr, weight_decay=wd)
        else:
            self.optimizer = AdamW(model.parameters(), lr=lr, weight_decay=wd)
            
        self.max_epochs = config.get("max_epochs", 100)
        
        # Warmup scheduler: linear warmup, then Cosine Annealing
        warmup_epochs = min(10, max(1, self.max_epochs // 10))
        if warmup_epochs >= self.max_epochs:
            warmup_epochs = max(1, self.max_epochs - 1)
            
        warmup_scheduler = LinearLR(self.optimizer, start_factor=0.1, end_factor=1.0, total_iters=warmup_epochs)
        t_max = max(1, self.max_epochs - warmup_epochs)
        cosine_scheduler = CosineAnnealingLR(self.optimizer, T_max=t_max, eta_min=1e-6)
        self.scheduler = SequentialLR(
            self.optimizer, 
            schedulers=[warmup_scheduler, cosine_scheduler], 
            milestones=[warmup_epochs]
        )
        
        import psutil
        import os
        ram_gb = psutil.virtual_memory().total / (1024 ** 3)
        bypass = os.environ.get("BYPASS_MEM_CHECK", "false").lower() == "true" or os.environ.get("FORCE_TRAIN", "false").lower() == "true"
        if ram_gb < 6.0:
            print(f"[WARNING] Available RAM is {ram_gb:.1f}GB. ST-GCN training is optimized for >=6GB.")
            if not bypass:
                print("[WARNING] Insufficient RAM. Training blocked to prevent OOM crash. Set env FORCE_TRAIN=True or BYPASS_MEM_CHECK=True to override.")
                raise MemoryError(f"Insufficient RAM ({ram_gb:.1f}GB < 6GB). Training blocked.")
            else:
                print("[WARNING] Insufficient RAM, but bypass flag set. Proceeding with risk of memory starvation.")
            
        dir_counts = config.get("direction_class_counts", [1, 1, 1, 1, 1])
        focal_gamma = config.get("focal_gamma", 2.0)
        label_smoothing = config.get("label_smoothing", 0.1)
        
        self.criterion = MultiTaskFocalLoss(
            direction_class_counts=dir_counts,
            gamma=focal_gamma,
            label_smoothing=label_smoothing
        ).to(self.device)
        
        self.grad_clip = config.get("grad_clip", 1.0)
        
        # Resolve workspace root and artifacts directory as absolute paths to prevent package installation side-effects
        import os
        from pathlib import Path
        
        current = Path(__file__).resolve()
        workspace_root = current
        for parent in current.parents:
            if (parent / ".git").exists() or (parent / "README.md").exists() or (parent / "ARCHITECTURE.md").exists():
                workspace_root = parent
                break
                
        artifacts_dir = os.path.abspath(workspace_root / "ml" / "artifacts")
        save_path = os.path.join(artifacts_dir, "best_model.pt")
        
        self.early_stopper = EarlyStopping(
            patience=config.get("early_stopping_patience", 15),
            save_path=save_path
        )
        self.checkpoint = ModelCheckpoint(checkpoint_dir=artifacts_dir)
        self.tracker = WandbTracker(config)
        
        # SAM does not easily support PyTorch AMP GradScaler in basic configurations
        # so we disable scaler when running SAM to maintain numerical stability.
        self.scaler = torch.cuda.amp.GradScaler() if torch.cuda.is_available() and not self.use_sam else None

    def attack_features(self, graph_sequence: list, loss: torch.Tensor, epsilon: float = 0.05) -> list:
        """Perturbs input node features in direction of gradients (FGM regularizer)."""
        grads = []
        for graph in graph_sequence:
            if graph.x.grad is not None:
                grads.append(graph.x.grad.data)
            else:
                grads.append(torch.zeros_like(graph.x))
                
        # Compute joint gradient norm
        flat_grads = torch.cat([g.view(-1) for g in grads])
        norm = torch.norm(flat_grads)
        
        perturbed_sequence = []
        if norm > 0:
            scale = epsilon / (norm + 1e-12)
            for graph in graph_sequence:
                perturbed_graph = graph.clone()
                if graph.x.grad is not None:
                    perturbed_graph.x = graph.x + graph.x.grad.data * scale
                perturbed_sequence.append(perturbed_graph)
        else:
            perturbed_sequence = graph_sequence
            
        return perturbed_sequence

    def train_epoch(self) -> dict:
        self.model.train()
        total_loss, total_dir_loss, total_vol_loss = 0.0, 0.0, 0.0
        
        batch_size = self.config.get("batch_size", 8)
        self.optimizer.zero_grad()
        
        batch_cache = []
        for idx, item in enumerate(self.train_graphs):
            # Format: (graph_seq, dir_labels, vol_labels, returns, vol_raw)
            graph_seq, dir_labels, vol_labels, returns = item[0], item[1], item[2], item[3]
            vol_raw = item[4] if len(item) > 4 else None
            
            # Move to device
            dir_labels = dir_labels.to(self.device)
            vol_labels = vol_labels.to(self.device)
            returns = returns.to(self.device)
            if vol_raw is not None:
                vol_raw = vol_raw.to(self.device)
                
            for g in graph_seq:
                g.x = g.x.detach().to(self.device)
                if self.use_fgm:
                    g.x.requires_grad_(True)
                else:
                    g.x.requires_grad_(False)
                    
            batch_cache.append((graph_seq, dir_labels, vol_labels, returns, vol_raw))
            
            # Perform optimization step when batch is complete or end of dataset is reached
            if len(batch_cache) == batch_size or (idx + 1) == len(self.train_graphs):
                effective_batch_size = len(batch_cache)
                
                if self.use_sam:
                    # ── SAM Optimization with Gradient Accumulation ──
                    # 1. First backward pass: accumulate gradients over clean weights
                    for b_g_seq, b_dir_labels, b_vol_labels, b_returns, b_vol_raw in batch_cache:
                        dir_logits, vol_logits, reg_ret, reg_vol = self.model(b_g_seq, return_all=True)
                        loss, dir_loss, vol_loss = self.criterion(
                            dir_logits, vol_logits, b_dir_labels, b_vol_labels,
                            reg_ret, reg_vol, b_returns, b_vol_raw
                        )
                        scaled_loss = loss / effective_batch_size
                        scaled_loss.backward()
                        
                        total_loss += loss.item()
                        total_dir_loss += dir_loss.item()
                        total_vol_loss += vol_loss.item()
                        
                    # Perturb weights based on clean gradients
                    self.optimizer.first_step(zero_grad=True)
                    
                    # 2. Second backward pass: accumulate gradients over perturbed weights
                    for b_g_seq, b_dir_labels, b_vol_labels, b_returns, b_vol_raw in batch_cache:
                        dir_logits2, vol_logits2, reg_ret2, reg_vol2 = self.model(b_g_seq, return_all=True)
                        loss_second, _, _ = self.criterion(
                            dir_logits2, vol_logits2, b_dir_labels, b_vol_labels,
                            reg_ret2, reg_vol2, b_returns, b_vol_raw
                        )
                        scaled_loss_second = loss_second / effective_batch_size
                        scaled_loss_second.backward()
                        
                    # Restore clean weights and step base optimizer using perturbed gradients
                    self.optimizer.second_step(zero_grad=True)
                    
                elif self.use_fgm:
                    # ── FGM Adversarial Optimization with Gradient Accumulation ──
                    for b_g_seq, b_dir_labels, b_vol_labels, b_returns, b_vol_raw in batch_cache:
                        # 1. Forward on clean features
                        dir_logits, vol_logits, reg_ret, reg_vol = self.model(b_g_seq, return_all=True)
                        loss_clean, dir_loss, vol_loss = self.criterion(
                            dir_logits, vol_logits, b_dir_labels, b_vol_labels,
                            reg_ret, reg_vol, b_returns, b_vol_raw
                        )
                        # Retain graph to perform second backward pass
                        loss_clean.backward(retain_graph=True)
                        
                        # 2. Perturb node features
                        perturbed_seq = self.attack_features(b_g_seq, loss_clean, epsilon=self.fgm_epsilon)
                        
                        # 3. Forward on adversarial features
                        dir_logits_adv, vol_logits_adv, reg_ret_adv, reg_vol_adv = self.model(perturbed_seq, return_all=True)
                        loss_adv, _, _ = self.criterion(
                            dir_logits_adv, vol_logits_adv, b_dir_labels, b_vol_labels,
                            reg_ret_adv, reg_vol_adv, b_returns, b_vol_raw
                        )
                        
                        # 4. Joint Loss
                        loss = 0.5 * loss_clean + 0.5 * loss_adv
                        scaled_loss = loss / effective_batch_size
                        scaled_loss.backward()
                        
                        total_loss += loss.item()
                        total_dir_loss += dir_loss.item()
                        total_vol_loss += vol_loss.item()
                        
                    clip_grad_norm_(self.model.parameters(), max_norm=self.grad_clip)
                    self.optimizer.step()
                    self.optimizer.zero_grad()
                    
                else:
                    # ── Standard AdamW Optimization with Gradient Accumulation ──
                    for b_g_seq, b_dir_labels, b_vol_labels, b_returns, b_vol_raw in batch_cache:
                        if self.scaler is not None:
                            with torch.amp.autocast('cuda'):
                                dir_logits, vol_logits, reg_ret, reg_vol = self.model(b_g_seq, return_all=True)
                                loss, dir_loss, vol_loss = self.criterion(
                                    dir_logits, vol_logits, b_dir_labels, b_vol_labels,
                                    reg_ret, reg_vol, b_returns, b_vol_raw
                                )
                            scaled_loss = loss / effective_batch_size
                            self.scaler.scale(scaled_loss).backward()
                        else:
                            dir_logits, vol_logits, reg_ret, reg_vol = self.model(b_g_seq, return_all=True)
                            loss, dir_loss, vol_loss = self.criterion(
                                dir_logits, vol_logits, b_dir_labels, b_vol_labels,
                                reg_ret, reg_vol, b_returns, b_vol_raw
                            )
                            scaled_loss = loss / effective_batch_size
                            scaled_loss.backward()
                            
                        total_loss += loss.item()
                        total_dir_loss += dir_loss.item()
                        total_vol_loss += vol_loss.item()
                        
                    if self.scaler is not None:
                        self.scaler.unscale_(self.optimizer)
                        clip_grad_norm_(self.model.parameters(), max_norm=self.grad_clip)
                        self.scaler.step(self.optimizer)
                        self.scaler.update()
                    else:
                        clip_grad_norm_(self.model.parameters(), max_norm=self.grad_clip)
                        self.optimizer.step()
                    self.optimizer.zero_grad()
                    
                # Reset batch cache
                batch_cache = []
                
        n = max(1, len(self.train_graphs))
        return {
            "train_loss": total_loss / n,
            "train_dir_loss": total_dir_loss / n,
            "train_vol_loss": total_vol_loss / n
        }

    def validate(self) -> dict:
        self.model.eval()
        total_loss, total_dir_loss, total_vol_loss = 0.0, 0.0, 0.0
        
        all_dir_labels = []
        all_dir_preds = []
        all_dir_probs = []
        all_returns = []
        
        with torch.no_grad():
            for item in self.val_graphs:
                graph_seq, dir_labels, vol_labels, returns = item[0], item[1], item[2], item[3]
                vol_raw = item[4] if len(item) > 4 else None
                
                graph_seq = [g.to(self.device) for g in graph_seq]
                dir_labels = dir_labels.to(self.device)
                vol_labels = vol_labels.to(self.device)
                returns = returns.to(self.device)
                if vol_raw is not None:
                    vol_raw = vol_raw.to(self.device)
                
                dir_logits, vol_logits, reg_ret, reg_vol = self.model(graph_seq, return_all=True)
                loss, dir_loss, vol_loss = self.criterion(
                    dir_logits, vol_logits, dir_labels, vol_labels,
                    reg_ret, reg_vol, returns, vol_raw
                )
                    
                total_loss += loss.item()
                total_dir_loss += dir_loss.item()
                total_vol_loss += vol_loss.item()
                
                probs = torch.softmax(dir_logits, dim=-1)
                preds = torch.argmax(probs, dim=-1)
                
                all_dir_labels.append(dir_labels.cpu().numpy())
                all_dir_preds.append(preds.cpu().numpy())
                all_dir_probs.append(probs.cpu().numpy())
                all_returns.append(returns.cpu().numpy() if isinstance(returns, torch.Tensor) else returns)
                
        n = max(1, len(self.val_graphs))
        metrics = {
            "val_loss": total_loss / n,
            "val_dir_loss": total_dir_loss / n,
            "val_vol_loss": total_vol_loss / n
        }
        
        if len(all_dir_labels) > 0:
            y_true = np.concatenate(all_dir_labels)
            y_pred = np.concatenate(all_dir_preds)
            y_prob = np.concatenate(all_dir_probs)
            ret_arr = np.concatenate(all_returns)
            
            # Calculate daily portfolio returns based on model signals
            signal_weights = np.zeros_like(y_pred, dtype=np.float32)
            signal_weights[y_pred == 2] = 1.0   # BUY
            signal_weights[y_pred == 1] = 0.0   # HOLD
            signal_weights[y_pred == 0] = -1.0  # SELL
            
            num_assets = y_pred.shape[0] // len(self.val_graphs)
            trade_returns = signal_weights * ret_arr
            trade_returns = trade_returns.reshape(-1, num_assets)
            daily_portfolio_returns = trade_returns.mean(axis=1)
            
            clf_metrics = compute_all_metrics(y_true, y_pred, y_prob, daily_portfolio_returns)
            metrics.update(clf_metrics)
            
        return metrics

    def fit(self) -> None:
        for epoch in range(self.max_epochs):
            train_metrics = self.train_epoch()
            val_metrics = self.validate()
            self.scheduler.step()
            
            combined_metrics = {**train_metrics, **val_metrics}
            self.tracker.log_epoch(epoch, combined_metrics)
            
            f1 = val_metrics.get("f1_macro", 0.0)
            sharpe = val_metrics.get("sharpe_ratio", 0.0)
            
            # Composite Metric: 0.6 * F1 + 0.4 * Sharpe (Sharpe normalized between 0 and 3)
            normalized_sharpe = max(0.0, min(1.0, sharpe / 3.0)) if sharpe > 0 else 0.0
            monitored_score = 0.6 * f1 + 0.4 * normalized_sharpe
            
            print(f"Epoch {epoch:3d} | Loss: {train_metrics['train_loss']:.4f} | Val F1: {f1:.4f} | Sharpe: {sharpe:.4f} | Monitored Score: {monitored_score:.4f}")
            
            self.checkpoint(epoch, monitored_score, self.model)
            
            # CPU/GPU Memory Optimization to prevent memory leakage and system crashes
            import gc
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                
            if self.early_stopper(monitored_score, self.model):
                break
                
        self.tracker.log_model_artifact(self.early_stopper.save_path)
        self.tracker.finish()
