"""
Runs inference on latest data. Called by FastAPI /api/inference/trigger endpoint.
Returns count of predictions stored and model version.
"""

def run_inference() -> dict:
    """
    1. Load latest 30 days of features from FeatureStore
    2. Build today's graph using DynamicGraphBuilder
    3. Load model from ml/artifacts/best_model.pt via STGCNModel.load()
    4. Run forward pass: dir_logits, vol_logits = model(graph_sequence)
    5. Compute predictions:
       direction = DIRECTION_CLASSES[argmax(softmax(dir_logits))]
       confidence = max(softmax(dir_logits)) * 100
       volatility = VOLATILITY_CLASSES[argmax(softmax(vol_logits))]
    6. Compute SHAP for each asset
    7. Upsert into predictions table for today
    8. Return {"predictions_stored": N, "model_version": version}
    """
    print("Running inference pipeline...")
    
    # Mock return
    return {
        "predictions_stored": 50,
        "model_version": "v1.0.0"
    }

if __name__ == "__main__":
    result = run_inference()
    print(f"✅ Inference complete: {result}")
