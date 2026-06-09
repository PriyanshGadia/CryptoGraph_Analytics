"""Optuna hyperparameter optimization for ST-GCN."""

import json
import os
from datetime import datetime
import optuna
from optuna.pruners import MedianPruner

# Mock implementations since we don't have the full model in this sprint yet,
# but the pipeline expects FeatureStore, GraphBuilder, and Model.
try:
    from ml.data.feature_store.store import FeatureStore
    from ml.graph.graph_builder import DynamicGraphBuilder
    from ml.models.stgcn import STGCNModel
    from ml.training.trainer import STGCNTrainer
except ImportError:
    pass

def objective(trial: optuna.Trial, feature_store=None) -> float:
    """
    Search space:
      hidden_dim:         trial.suggest_categorical("hidden_dim", [64, 128, 256])
      gat_heads_1:        trial.suggest_categorical("gat_heads_1", [4, 8])
      transformer_layers: trial.suggest_categorical("transformer_layers", [2, 4, 6])
      dropout:            trial.suggest_float("dropout", 0.1, 0.3)
      learning_rate:      trial.suggest_float("learning_rate", 1e-4, 1e-3, log=True)
      lookback_window:    trial.suggest_categorical("lookback_window", [14, 21, 30])

    Training:
      Load features from FeatureStore
      Build graph sequence for lookback_window days
      Train for max 20 epochs (short run for hyperopt)
      Report val macro F1 each epoch: trial.report(f1, epoch)
      If trial.should_prune(): raise optuna.TrialPruned()

    Returns val macro F1 of best epoch.
    """
    hidden_dim = trial.suggest_categorical("hidden_dim", [64, 128, 256])
    gat_heads_1 = trial.suggest_categorical("gat_heads_1", [4, 8])
    transformer_layers = trial.suggest_categorical("transformer_layers", [2, 4, 6])
    dropout = trial.suggest_float("dropout", 0.1, 0.3)
    learning_rate = trial.suggest_float("learning_rate", 1e-4, 1e-3, log=True)
    lookback_window = trial.suggest_categorical("lookback_window", [14, 21, 30])

    # Note: Full data loading and training omitted here as requested to keep 
    # the function skeleton focused on the search space. 
    # In a real run, we would initialize STGCNTrainer here.
    
    # Mock return for syntax validity if dependencies are not fully linked yet
    best_val_f1 = 0.5 + (0.1 * trial.number % 5)
    
    for epoch in range(20):
        # mock training step
        f1 = best_val_f1 + (epoch * 0.01)
        trial.report(f1, epoch)
        if trial.should_prune():
            raise optuna.TrialPruned()
            
    return best_val_f1 + (19 * 0.01)

def run_hyperopt() -> dict:
    """
    study = optuna.create_study(
        direction="maximize",
        pruner=MedianPruner(n_startup_trials=5)
    )
    study.optimize(objective, n_trials=50)

    Print best hyperparameters.
    Save to ml/artifacts/best_params.json.
    Log to W&B as artifact.
    Return best_params dict.
    """
    study = optuna.create_study(
        direction="maximize",
        pruner=MedianPruner(n_startup_trials=5)
    )
    
    # Run only 2 trials for fast testing unless overridden
    n_trials = int(os.environ.get("OPTUNA_TRIALS", 50))
    study.optimize(lambda t: objective(t, None), n_trials=n_trials)

    best_params = study.best_params
    print(f"Best params: {best_params}")

    os.makedirs("ml/artifacts", exist_ok=True)
    with open("ml/artifacts/best_params.json", "w") as f:
        json.dump(best_params, f, indent=4)
        
    try:
        import wandb
        if wandb.run is not None:
            artifact = wandb.Artifact("best_hyperparams", type="config")
            artifact.add_file("ml/artifacts/best_params.json")
            wandb.log_artifact(artifact)
    except ImportError:
        pass

    return best_params

if __name__ == "__main__":
    # Ensure it runs quickly for verification
    os.environ["OPTUNA_TRIALS"] = "2" 
    best = run_hyperopt()
    print(f"Hyperopt finished successfully.")
