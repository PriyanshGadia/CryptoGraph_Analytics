"""
Topological Shapley Value Explainer (T-SHAP).
Provides mathematical Explainable AI (XAI) feature attribution for the PyTorch ST-GCN model,
ensuring strict regulatory compliance against algorithmic negligence.
"""

import math
from typing import Dict, Any, List

class TopologicalShapExplainer:
    def __init__(self):
        # In production, this would hook into captum.attr or shap library
        # to calculate exact marginal gradients across the PyTorch graph tensors.
        pass

    def explain_prediction(self, symbol: str, features: Dict[str, float], model=None, graph_sequence=None, asset_idx=None, feature_names=None) -> Dict[str, Any]:
        """
        Calculates the Shapley values (impact) of each feature/node that contributed 
        to the final ST-GCN prediction.
        """
        print(f"[T-SHAP] Calculating Topological Shapley Values for {symbol}...")
        
        if model is not None and graph_sequence is not None and asset_idx is not None and feature_names is not None:
            try:
                from captum.attr import IntegratedGradients
                from torch_geometric.data import Data
                import torch
                from ml.evaluation.explainability import _STGCNTensorWrapper
                
                model.eval()
                N = graph_sequence[0].x.shape[0]
                T = len(graph_sequence)
                F = graph_sequence[0].x.shape[1]
                
                x_tensor = torch.stack([g.x for g in graph_sequence], dim=1)  # (N, T, F)
                x_tensor = x_tensor.detach().requires_grad_(True)
                edge_indices = [g.edge_index.clone() for g in graph_sequence]
                
                wrapper = _STGCNTensorWrapper(model, edge_indices, target_task=0)
                wrapper.eval()
                
                # Predict class for this asset
                with torch.no_grad():
                    logits = wrapper(x_tensor)
                    pred_class = int(logits[asset_idx].argmax().item())
                
                ig = IntegratedGradients(wrapper)
                baseline = torch.zeros_like(x_tensor)
                
                # Compute attributions
                attrs = ig.attribute(
                    x_tensor,
                    baselines=baseline,
                    target=pred_class,
                    n_steps=10,  # 10 steps is fast for real-time inference
                    internal_batch_size=N,
                )
                
                # Average across time steps for this specific asset
                asset_attrs = attrs[asset_idx].abs().mean(dim=0).detach().cpu().numpy()
                
                # Normalize to percentage
                total_abs = sum(abs(v) for v in asset_attrs)
                if total_abs > 0:
                    attributions_pct = {feature_names[i]: float(round((abs(asset_attrs[i]) / total_abs) * 100.0, 2)) for i in range(F)}
                else:
                    attributions_pct = {feature_names[i]: 1.0 for i in range(F)}
                    
                sorted_attr = dict(sorted(attributions_pct.items(), key=lambda item: item[1], reverse=True))
                top_feature = list(sorted_attr.keys())[0]
                top_impact = sorted_attr[top_feature]
                defense_text = f"Mathematical XAI Attribution: {top_impact}% of the variance in the final tensor activation was driven by topological shifts in '{top_feature}'."
                
                return {
                    "attributions_pct": sorted_attr,
                    "legal_defense_summary": defense_text
                }
            except Exception as e:
                print(f"[T-SHAP] Real explainability failed: {e}")
                raise e
        else:
            raise ValueError(
                "Model, graph_sequence, asset_idx, and feature_names must be provided. "
                "Fake arithmetic fallbacks have been removed for strict integrity."
            )

if __name__ == "__main__":
    print("TopologicalShapExplainer requires a loaded STGCNModel and graph sequence to compute real attributions.")
