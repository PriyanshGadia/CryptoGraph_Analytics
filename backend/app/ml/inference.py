"""
CryptoGraph ML Inference Bridge

This module acts as the API bridge between the FastAPI backend and the core ML pipeline 
(ST-GCN model) located in the `ml/` directory. By importing the ML pipeline directly,
we ensure the backend is tightly coupled with the model predictions as the Single Source of Truth.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger("cryptograph.inference")

def run_ml_inference() -> Dict[str, Any]:
    """
    Executes the full ST-GCN inference pipeline.
    This triggers feature generation, graph construction, and model forward passes
    to produce the latest market forecasts.
    
    Returns:
        Dict containing prediction results and performance metrics.
    """
    try:
        from ml.pipelines.inference_pipeline import run_inference
        logger.info("Triggering ML inference pipeline...")
        results = run_inference()
        logger.info("ML inference pipeline completed successfully.")
        return results
    except ImportError:
        logger.error("ML module could not be imported. Ensure the 'ml' directory is in PYTHONPATH.")
        raise
    except Exception as e:
        logger.error(f"ML inference pipeline failed: {e}", exc_info=True)
        raise
