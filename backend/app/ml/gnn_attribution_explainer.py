import torch


class GNNGradientAttributionExplainer:
    """
    Integrated Gradients attribution for the STGCN model's node features.
    Attributes the model's prediction for a given asset back to its input
    features by integrating gradients along a straight-line path from a
    zero baseline to the actual input (Sundararajan et al., 2017).
    """

    def __init__(self, steps: int = 8):
        self.steps = steps

    def explain_prediction(self, symbol, features, model, graph_sequence, asset_idx, feature_names):
        model.eval()
        last_graph = graph_sequence[-1]
        x = last_graph.x[asset_idx].detach().clone()
        baseline = torch.zeros_like(x)

        total_gradients = torch.zeros_like(x)
        original_x = last_graph.x
        
        for step in range(1, self.steps + 1):
            alpha = step / self.steps
            interpolated = baseline + alpha * (x - baseline)
            interpolated.requires_grad_(True)

            # Efficiently replace the feature tensor without cloning the whole graph object
            new_x = original_x.clone()
            new_x[asset_idx] = interpolated
            last_graph.x = new_x

            if hasattr(model, "reg_head"):
                # Enterprise regression model expects a list of sequences: [graph_sequence]
                # it outputs pred of shape [1, num_nodes] (since B=1)
                pred = model([graph_sequence], return_uncertainty=False)
                target_val = pred[0, asset_idx]
            else:
                dir_logits, _ = model(graph_sequence)
                target_val = dir_logits[asset_idx].max()
 
            grad = torch.autograd.grad(target_val, interpolated, retain_graph=False, create_graph=False)[0]
            total_gradients += grad.detach()

        # Restore original tensor
        last_graph.x = original_x
        
        avg_gradients = total_gradients / self.steps
        attributions = (x - baseline) * avg_gradients  # (feature_dim,)

        attr_np = attributions.cpu().numpy()
        total_abs = float(sum(abs(v) for v in attr_np)) or 1.0
        result = {}
        for i, name in enumerate(feature_names[: len(attr_np)]):
            result[name] = float(attr_np[i])
        result["attributions_pct"] = {
            name: round(100.0 * abs(attr_np[i]) / total_abs, 2)
            for i, name in enumerate(feature_names[: len(attr_np)])
        }
        return result
