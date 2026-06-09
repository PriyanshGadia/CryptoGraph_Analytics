import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from ml.evaluation.finance_metrics import compute_all_finance_metrics

DIRECTION_CLASS_NAMES  = ["strong_up", "up", "neutral", "down", "strong_down"]
VOLATILITY_CLASS_NAMES = ["low", "medium", "high", "extreme"]

def compute_all_metrics(
    y_true: np.ndarray,    # integer class labels
    y_pred: np.ndarray,    # integer class predictions
    y_prob: np.ndarray,    # probability matrix (N, 5)
    returns: np.ndarray    # actual daily returns for finance metrics
) -> dict:
    """
    Returns flat dict with all metrics:

    Classification (using sklearn):
      accuracy, precision_macro, recall_macro, f1_macro,
      roc_auc_macro (multi_class='ovr', average='macro'),
      per_class_f1: dict mapping class_name -> f1 score

    Finance (from compute_all_finance_metrics):
      sharpe_ratio, sortino_ratio, max_drawdown,
      profit_factor, win_rate
    """
    acc = float(accuracy_score(y_true, y_pred))
    prec = float(precision_score(y_true, y_pred, average="macro", zero_division=0))
    rec = float(recall_score(y_true, y_pred, average="macro", zero_division=0))
    f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    
    try:
        roc_auc = float(roc_auc_score(y_true, y_prob, multi_class="ovr", average="macro"))
    except ValueError:
        roc_auc = 0.5  # Fallback if only 1 class is present in y_true
        
    per_class = f1_score(y_true, y_pred, average=None, zero_division=0)
    per_class_f1 = {}
    
    # We map what we can. If y_true doesn't have all classes, length might differ.
    # Actually, f1_score(average=None) returns scores for all unique labels in y_true and y_pred.
    # To be safe, specify labels parameter to force full length.
    n_classes = y_prob.shape[1]
    full_per_class = f1_score(y_true, y_pred, labels=list(range(n_classes)), average=None, zero_division=0)
    
    for i, score in enumerate(full_per_class):
        name = DIRECTION_CLASS_NAMES[i] if i < len(DIRECTION_CLASS_NAMES) else f"class_{i}"
        per_class_f1[name] = float(score)

    fin_metrics = compute_all_finance_metrics(pd.Series(returns))

    metrics = {
        "accuracy": acc,
        "precision_macro": prec,
        "recall_macro": rec,
        "f1_macro": f1,
        "roc_auc_macro": roc_auc,
        "per_class_f1": per_class_f1
    }
    
    metrics.update(fin_metrics)
    return metrics
