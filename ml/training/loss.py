import torch
import torch.nn as nn
from torch import Tensor
from typing import Tuple, List

class MultiTaskLoss(nn.Module):
    """
    Combined weighted loss for both prediction heads.

    direction_loss:  CrossEntropyLoss with inverse class frequency weights
    volatility_loss: CrossEntropyLoss with equal class weights
    total_loss:      0.7 * direction_loss + 0.3 * volatility_loss
    """
    def __init__(self, direction_class_counts: List[int]):
        """
        direction_class_counts: list of 5 ints, one per direction class
        Computes inverse frequency weights: w_i = total / (n_classes * count_i)
        """
        super().__init__()
        counts = torch.tensor(direction_class_counts, dtype=torch.float)
        total = counts.sum()
        
        # Prevent division by zero if count is 0
        eps = 1e-8
        dir_weights = total / (len(counts) * (counts + eps))
        
        self.direction_loss_fn = nn.CrossEntropyLoss(weight=dir_weights)
        self.volatility_loss_fn = nn.CrossEntropyLoss()  # equal weights

    def forward(
        self,
        direction_logits: Tensor,   # (N, 5)
        volatility_logits: Tensor,  # (N, 4)
        direction_labels: Tensor,   # (N,) long
        volatility_labels: Tensor   # (N,) long
    ) -> Tuple[Tensor, Tensor, Tensor]:
        """Returns (total_loss, direction_loss, volatility_loss)"""
        dir_loss = self.direction_loss_fn(direction_logits, direction_labels)
        vol_loss = self.volatility_loss_fn(volatility_logits, volatility_labels)
        
        total = 0.7 * dir_loss + 0.3 * vol_loss
        return total, dir_loss, vol_loss
