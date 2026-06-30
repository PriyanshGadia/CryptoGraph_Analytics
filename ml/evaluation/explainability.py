"""Captum-based explainability for ST-GCN predictions.

Replaces the previous pre-computed SHAP pipeline with real gradient-based
attribution via Captum IntegratedGradients.  A thin wrapper module
(``_STGCNTensorWrapper``) bridges the gap between Captum's requirement
for a single dense input tensor and the GNN's native list-of-graphs
interface.
"""

import os
from typing import Dict, List, Optional

import torch
import torch.nn as nn
import numpy as np
import matplotlib.pyplot as plt
from torch import Tensor
from torch_geometric.data import Data
from captum.attr import IntegratedGradients


class _STGCNTensorWrapper(nn.Module):
    """Differentiable wrapper that accepts a dense (N, T, F) tensor and
    reconstructs the ``list[Data]`` graph sequence that ``STGCNModel``
    expects.

    Parameters
    ----------
    model : nn.Module
        The trained ``STGCNModel`` instance (kept frozen — no parameter
        copies are made).
    edge_indices : list[Tensor]
        One ``edge_index`` tensor per timestep, extracted from the
        original graph sequence.  These are registered as buffers so
        they travel with the module to the correct device.
    target_task : int
        ``0`` → direction logits, ``1`` → volatility logits.
    """

    def __init__(
        self,
        model: nn.Module,
        edge_indices: List[Tensor],
        target_task: int = 0,
    ):
        super().__init__()
        self.model = model
        self.target_task = target_task
        # Store edge indices as named buffers for device tracking.
        for t, ei in enumerate(edge_indices):
            self.register_buffer(f"_ei_{t}", ei)
        self._num_steps = len(edge_indices)

    def forward(self, x: Tensor) -> Tensor:
        """
        Parameters
        ----------
        x : Tensor
            Shape ``(N, T, F)`` — the node-feature cube.

        Returns
        -------
        Tensor
            Logits for the selected task head, shape ``(N, C)``.
        """
        graph_sequence: list[Data] = []
        for t in range(self._num_steps):
            ei = getattr(self, f"_ei_{t}")
            graph_sequence.append(Data(x=x[:, t, :], edge_index=ei))

        dir_logits, vol_logits = self.model(graph_sequence)
        return dir_logits if self.target_task == 0 else vol_logits


def compute_attributions(
    model: nn.Module,
    graph_sequence: List[Data],
    feature_names: List[str],
    target_class: Optional[int] = None,
    target_task: int = 0,
    n_steps: int = 50,
) -> Dict[str, float]:
    """Compute real gradient-based feature importances using Captum
    IntegratedGradients.

    Parameters
    ----------
    model : nn.Module
        A trained ``STGCNModel``.
    graph_sequence : list[Data]
        The T-length sequence of ``torch_geometric.data.Data`` graphs
        that the model normally ingests.
    feature_names : list[str]
        Human-readable names for the F input features (length must equal
        ``graph_sequence[0].x.shape[1]``).
    target_class : int | None
        Class index to attribute towards.  ``None`` → use the model's
        argmax prediction.
    target_task : int
        ``0`` for direction, ``1`` for volatility.
    n_steps : int
        Number of interpolation steps for Integrated Gradients.

    Returns
    -------
    dict[str, float]
        ``{feature_name: mean_abs_attribution}`` sorted descending.
    """
    model.eval()

    N = graph_sequence[0].x.shape[0]
    T = len(graph_sequence)
    F = graph_sequence[0].x.shape[1]

    # Stack node features into a single dense tensor (N, T, F).
    x_tensor = torch.stack([g.x for g in graph_sequence], dim=1)  # (N, T, F)
    x_tensor = x_tensor.detach().requires_grad_(True)

    # Collect edge indices from every timestep.
    edge_indices = [g.edge_index.clone() for g in graph_sequence]

    wrapper = _STGCNTensorWrapper(model, edge_indices, target_task=target_task)
    wrapper.eval()

    # Resolve target class via a forward pass if not provided.
    if target_class is None:
        with torch.no_grad():
            logits = wrapper(x_tensor)
            # Per-node argmax averaged — pick the dominant class.
            target_class = int(logits.mean(dim=0).argmax().item())

    ig = IntegratedGradients(wrapper)

    # Baseline: zero tensor (absence of signal).
    baseline = torch.zeros_like(x_tensor)

    # Attributions shape: (N, T, F)
    attrs = ig.attribute(
        x_tensor,
        baselines=baseline,
        target=target_class,
        n_steps=n_steps,
        internal_batch_size=N,
    )

    # Average absolute attributions across nodes (N) and timesteps (T)
    # to produce a single importance score per feature.
    # attrs: (N, T, F) → mean over N and T → (F,)
    mean_abs = attrs.abs().mean(dim=(0, 1)).detach().cpu().numpy()  # (F,)

    raw_dict = {feature_names[i]: float(mean_abs[i]) for i in range(F)}
    sorted_dict = dict(
        sorted(raw_dict.items(), key=lambda item: abs(item[1]), reverse=True)
    )
    return sorted_dict


def get_top_features(attr_dict: Dict[str, float], top_k: int = 5) -> Dict[str, float]:
    """Returns top_k features by absolute attribution value."""
    top_keys = list(attr_dict.keys())[:top_k]
    return {k: attr_dict[k] for k in top_keys}


def explain_all_assets(
    model: nn.Module,
    graph_sequences: Dict[str, List[Data]],
    feature_names: List[str],
    db_session=None,
) -> None:
    """Compute Captum attributions for every asset and persist them.

    For each asset:
      1. Compute IntegratedGradients attributions.
      2. Extract the top-5 features.
      3. Update the ``predictions`` table with real feature importances.

    A global summary bar chart is saved to ``ml/artifacts/attr_summary.png``.

    Parameters
    ----------
    model : nn.Module
        Trained ``STGCNModel``.
    graph_sequences : dict[str, list[Data]]
        ``{symbol: graph_sequence}`` mapping.
    feature_names : list[str]
        The 24 input feature names.
    db_session : SQLAlchemy Session | None
        If provided, updates the ``predictions.shap_values`` column
        for the latest prediction of each asset.
    """
    global_attrs: Dict[str, float] = {feat: 0.0 for feat in feature_names}

    for symbol, seq in graph_sequences.items():
        attrs = compute_attributions(model, seq, feature_names)
        top_5 = get_top_features(attrs, top_k=5)
        top_feature = list(top_5.keys())[0]

        # Accumulate global importances.
        for k, v in attrs.items():
            global_attrs[k] += abs(v)

        print(f"Attribution computed for {symbol}: top feature = {top_feature}")

        if db_session is not None:
            try:
                from app.db.models_sqla import Asset, Prediction
                from sqlalchemy import desc

                asset = (
                    db_session.query(Asset)
                    .filter(Asset.symbol == symbol)
                    .first()
                )
                if asset:
                    pred = (
                        db_session.query(Prediction)
                        .filter(Prediction.asset_id == asset.id)
                        .order_by(desc(Prediction.predicted_at))
                        .first()
                    )
                    if pred:
                        pred.shap_values = top_5
                        db_session.commit()
            except Exception as e:
                print(f"Error updating attributions in DB for {symbol}: {e}")

    # --- Global summary chart ---
    os.makedirs("ml/artifacts", exist_ok=True)

    n_assets = max(1, len(graph_sequences))
    for k in global_attrs:
        global_attrs[k] /= n_assets

    sorted_global = dict(
        sorted(global_attrs.items(), key=lambda item: item[1], reverse=True)
    )

    top_15_keys = list(sorted_global.keys())[:15][::-1]
    top_15_vals = [sorted_global[k] for k in top_15_keys[::-1]][::-1]

    plt.figure(figsize=(10, 8))
    plt.barh(top_15_keys, top_15_vals, color="dodgerblue")
    plt.title("Global Feature Attribution (Top 15 — IntegratedGradients)")
    plt.xlabel("Mean |Attribution|")
    plt.tight_layout()
    plt.savefig("ml/artifacts/attr_summary.png")
    plt.close()
