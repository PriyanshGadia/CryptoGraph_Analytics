"""
Focal Loss (Lin et al. 2017) with label smoothing for multi-task learning.

Addresses class imbalance by reducing the loss contribution from easy
(well-classified) examples, focusing the model on hard examples.

FL(p_t) = -alpha_t * (1 - p_t)^gamma * log(p_t)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor
from typing import Tuple, List, Optional


class FocalLoss(nn.Module):
    """Focal Loss with per-class alpha weights and label smoothing.

    Parameters
    ----------
    alpha : Tensor or None
        Per-class weight tensor. If None, uniform weights.
    gamma : float
        Focusing parameter. gamma=0 reduces to standard CE. gamma=2 is typical.
    label_smoothing : float
        Label smoothing epsilon. 0.0 = no smoothing, 0.1 = typical.
    """

    def __init__(
        self,
        alpha: Optional[Tensor] = None,
        gamma: float = 2.0,
        label_smoothing: float = 0.1,
    ):
        super().__init__()
        self.gamma = gamma
        self.label_smoothing = label_smoothing
        if alpha is not None:
            self.register_buffer("alpha", alpha)
        else:
            self.alpha = None

    def forward(self, logits: Tensor, targets: Tensor) -> Tensor:
        """
        logits: (N, C) raw model outputs
        targets: (N,) integer class labels
        """
        num_classes = logits.shape[1]

        # Apply label smoothing to one-hot targets
        with torch.no_grad():
            one_hot = torch.zeros_like(logits)
            one_hot.scatter_(1, targets.unsqueeze(1), 1.0)
            if self.label_smoothing > 0:
                one_hot = one_hot * (1.0 - self.label_smoothing) + \
                          self.label_smoothing / num_classes

        # Compute log-softmax for numerical stability
        log_probs = F.log_softmax(logits, dim=1)
        probs = log_probs.exp()

        # Focal modulation: (1 - p_t)^gamma
        # p_t is the probability of the correct class
        p_t = (probs * one_hot).sum(dim=1)  # (N,)
        focal_weight = (1.0 - p_t) ** self.gamma  # (N,)

        # Weighted cross entropy
        loss = -(one_hot * log_probs).sum(dim=1)  # (N,)

        # Apply focal weight
        loss = focal_weight * loss

        # Apply per-class alpha weights
        if self.alpha is not None:
            alpha_t = self.alpha[targets]  # (N,)
            loss = alpha_t * loss

        return loss.mean()


class MultiTaskFocalLoss(nn.Module):
    """
    Combined weighted loss for both prediction heads. Supports joint multi-task
    auxiliary regression regularizers if regression predictions and targets are provided.

    Loss Weights (Classification Only):
      0.7 * direction_loss + 0.3 * volatility_loss
      
    Loss Weights (Joint Classification & Regression Regularization):
      0.5 * direction_loss + 0.2 * volatility_loss + 0.2 * return_reg_loss + 0.1 * vol_reg_loss
    """

    def __init__(
        self,
        direction_class_counts: List[int],
        gamma: float = 2.0,
        label_smoothing: float = 0.1,
        dir_weight: float = 0.7,
    ):
        super().__init__()
        self.dir_weight = dir_weight
        self.vol_weight = 1.0 - dir_weight

        # Compute inverse frequency weights for direction classes
        counts = torch.tensor(direction_class_counts, dtype=torch.float)
        total = counts.sum()
        eps = 1e-8
        dir_alpha = total / (len(counts) * (counts + eps))
        # Normalize so alpha sums to num_classes (prevents gradient scale issues)
        dir_alpha = dir_alpha / dir_alpha.sum() * len(counts)

        self.direction_loss_fn = FocalLoss(
            alpha=dir_alpha,
            gamma=gamma,
            label_smoothing=label_smoothing,
        )
        self.volatility_loss_fn = nn.CrossEntropyLoss()  # equal weights
        self.reg_loss_fn = nn.MSELoss()  # MSE for auxiliary tasks

    def forward(
        self,
        direction_logits: Tensor,   # (N, 3)
        volatility_logits: Tensor,  # (N, 4)
        direction_labels: Tensor,   # (N,) long
        volatility_labels: Tensor,  # (N,) long
        reg_returns_pred: Optional[Tensor] = None,
        reg_vol_pred: Optional[Tensor] = None,
        reg_returns_true: Optional[Tensor] = None,
        reg_vol_true: Optional[Tensor] = None
    ) -> Tuple[Tensor, Tensor, Tensor]:
        """Returns (total_loss, direction_loss, volatility_loss)"""
        dir_loss = self.direction_loss_fn(direction_logits, direction_labels)
        vol_loss = self.volatility_loss_fn(volatility_logits, volatility_labels)

        has_reg = False
        if reg_returns_pred is not None:
            if reg_returns_true is not None:
                if reg_vol_pred is not None:
                    if reg_vol_true is not None:
                        has_reg = True

        if has_reg:
            ret_reg_loss = self.reg_loss_fn(reg_returns_pred, reg_returns_true)
            vol_reg_loss = self.reg_loss_fn(reg_vol_pred, reg_vol_true)
            total = 0.5 * dir_loss + 0.2 * vol_loss + 0.2 * ret_reg_loss + 0.1 * vol_reg_loss
        else:
            # Classification-only loss fallback
            total = self.dir_weight * dir_loss + self.vol_weight * vol_loss
            
        return total, dir_loss, vol_loss
