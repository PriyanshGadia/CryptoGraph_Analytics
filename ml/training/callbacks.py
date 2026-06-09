import os
import torch

class EarlyStopping:
    """Monitors val_f1_macro. Stops if no improvement for `patience` epochs."""

    def __init__(self, patience: int = 10, save_path: str = "ml/artifacts/best_model.pt"):
        self.patience    = patience
        self.save_path   = save_path
        self.best_score  = -float("inf")
        self.counter     = 0
        self.should_stop = False
        
        os.makedirs(os.path.dirname(self.save_path), exist_ok=True)

    def __call__(self, val_f1: float, model) -> bool:
        """
        Call each epoch with current val F1 score and model.
        If improved: save model to save_path, reset counter.
        If not improved: increment counter.
        If counter >= patience: set should_stop=True, print message.
        Returns True if training should stop.
        """
        if val_f1 > self.best_score:
            self.best_score = val_f1
            self.counter = 0
            torch.save(model.state_dict(), self.save_path)
        else:
            self.counter += 1
            if self.counter >= self.patience:
                self.should_stop = True
                print(f"Early stopping triggered. No improvement for {self.patience} epochs.")
                
        return self.should_stop

class ModelCheckpoint:
    """Saves checkpoint every 5 epochs, keeps only best 3 by val F1."""

    def __init__(
        self,
        checkpoint_dir: str = "ml/artifacts",
        save_every_n_epochs: int = 5,
        keep_top_k: int = 3
    ):
        self.checkpoint_dir = checkpoint_dir
        self.save_every_n_epochs = save_every_n_epochs
        self.keep_top_k = keep_top_k
        self.checkpoints = [] # List of tuples (val_f1, filepath)
        
        os.makedirs(self.checkpoint_dir, exist_ok=True)

    def __call__(self, epoch: int, val_f1: float, model) -> None:
        """
        If epoch % save_every_n_epochs == 0:
          Save to: {checkpoint_dir}/checkpoint_epoch_{epoch}_f1_{val_f1:.4f}.pt
        Keep only top-k checkpoints by val_f1 score (delete others).
        """
        if epoch % self.save_every_n_epochs == 0:
            filepath = os.path.join(self.checkpoint_dir, f"checkpoint_epoch_{epoch}_f1_{val_f1:.4f}.pt")
            torch.save(model.state_dict(), filepath)
            
            self.checkpoints.append((val_f1, filepath))
            # Sort descending by val_f1
            self.checkpoints.sort(key=lambda x: x[0], reverse=True)
            
            # Remove worst if we exceed keep_top_k
            while len(self.checkpoints) > self.keep_top_k:
                _, path_to_remove = self.checkpoints.pop()
                if os.path.exists(path_to_remove):
                    os.remove(path_to_remove)
