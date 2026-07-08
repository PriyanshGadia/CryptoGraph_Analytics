"""
Integration test for ML inference pipeline.
Verifies model loading, calibrated confidence scoring, and DB predictions storage.
"""

import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

import sqlite3
import pytest
import torch
from ml.pipelines.inference_pipeline import run_inference, DB_PATH

def test_inference_pipeline_execution():
    res = run_inference()
    assert isinstance(res, dict)
    assert "predictions_stored" in res
    assert res["predictions_stored"] > 0
    assert "model_version" in res

    from app.db.database import execute_with_retry

    def query_rows():
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("""
            SELECT assets.symbol, predictions.direction, predictions.confidence, predictions.model_version 
            FROM predictions 
            JOIN assets ON predictions.asset_id = assets.id 
            ORDER BY predictions.predicted_at DESC LIMIT 10
        """)
        res = cursor.fetchall()
        conn.close()
        return res

    rows = execute_with_retry(query_rows)

    assert len(rows) > 0, "No predictions found in cryptograph.db"
    for symbol, direction, confidence, version in rows:
        assert isinstance(symbol, str)
        assert isinstance(direction, str)
        assert 0.0 <= confidence <= 100.0, f"Confidence {confidence} for {symbol} out of range [0, 100]"
