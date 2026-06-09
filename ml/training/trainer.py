import torch
import numpy as np
from typing import List, Dict, Tuple
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.nn.utils import clip_grad_norm_

from ml.training.loss import MultiTaskLoss
from ml.training.callbacks import EarlyStopping, ModelCheckpoint
from ml.experiments.wandb_tracker import WandbTracker
from ml.training.metrics import compute_all_metrics
from ml.models.stgcn import STGCNModel

class STGCNTrainer:
    """Full training loop for the ST-GCN model."""

    def __init__(
        self,
        model: STGCNModel,
        train_graphs: List[Tuple], # list of (graph_sequence, direction_labels, vol_labels, returns)
        val_graphs: List[Tuple],   # same format
        config: dict
    ):
        self.model = model
        self.train_graphs = train_graphs
        self.val_graphs = val_graphs
        self.config = config
        
        self.device = next(model.parameters()).device
        
        self.optimizer = AdamW(
            model.parameters(), 
            lr=config.get("lr", 1e-3), 
            weight_decay=config.get("weight_decay", 1e-4)
        )
        self.max_epochs = config.get("max_epochs", 100)
        self.scheduler = CosineAnnealingLR(self.optimizer, T_max=50)
        
        dir_counts = config.get("direction_class_counts", [1, 1, 1, 1, 1])
        self.criterion = MultiTaskLoss(dir_counts).to(self.device)
        
        self.grad_clip = config.get("grad_clip", 1.0)
        
        self.early_stopper = EarlyStopping(patience=config.get("early_stopping_patience", 10))
        self.checkpoint = ModelCheckpoint()
        self.tracker = WandbTracker(config)

    def train_epoch(self) -> dict:
        self.model.train()
        total_loss, total_dir_loss, total_vol_loss = 0.0, 0.0, 0.0
        
        for graph_seq, dir_labels, vol_labels, returns in self.train_graphs:
            self.optimizer.zero_grad()
            
            # Move data to device
            graph_seq = [g.to(self.device) for g in graph_seq]
            dir_labels = dir_labels.to(self.device)
            vol_labels = vol_labels.to(self.device)
            
            if torch.cuda.is_available():
                with torch.cuda.amp.autocast():
                    dir_logits, vol_logits = self.model(graph_seq)
                    loss, dir_loss, vol_loss = self.criterion(dir_logits, vol_logits, dir_labels, vol_labels)
            else:
                dir_logits, vol_logits = self.model(graph_seq)
                loss, dir_loss, vol_loss = self.criterion(dir_logits, vol_logits, dir_labels, vol_labels)
                
            loss.backward()
            clip_grad_norm_(self.model.parameters(), max_norm=self.grad_clip)
            self.optimizer.step()
            
            total_loss += loss.item()
            total_dir_loss += dir_loss.item()
            total_vol_loss += vol_loss.item()
            
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
            for graph_seq, dir_labels, vol_labels, returns in self.val_graphs:
                graph_seq = [g.to(self.device) for g in graph_seq]
                dir_labels = dir_labels.to(self.device)
                vol_labels = vol_labels.to(self.device)
                
                if torch.cuda.is_available():
                    with torch.cuda.amp.autocast():
                        dir_logits, vol_logits = self.model(graph_seq)
                        loss, dir_loss, vol_loss = self.criterion(dir_logits, vol_logits, dir_labels, vol_labels)
                else:
                    dir_logits, vol_logits = self.model(graph_seq)
                    loss, dir_loss, vol_loss = self.criterion(dir_logits, vol_logits, dir_labels, vol_labels)
                    
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
            
            clf_metrics = compute_all_metrics(y_true, y_pred, y_prob, ret_arr)
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
            
            print(f"Epoch {epoch:3d} | Loss: {train_metrics['train_loss']:.4f} | Val F1: {f1:.4f}")
            
            self.checkpoint(epoch, f1, self.model)
            if self.early_stopper(f1, self.model):
                break
                
        self.tracker.log_model_artifact(self.early_stopper.save_path)
        self.tracker.finish()
