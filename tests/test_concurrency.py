"""
Unit test for SQLite database retry wrapper and WAL mode concurrency resilience.
"""

import sys
import sqlite3
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

import pytest
from backend.app.db.database import execute_with_retry

def test_execute_with_retry_success():
    call_count = 0
    def sample_action():
        nonlocal call_count
        call_count += 1
        return "success"

    res = execute_with_retry(sample_action, max_retries=3, backoff_seconds=0.01)
    assert res == "success"
    assert call_count == 1

def test_execute_with_retry_recover():
    call_count = 0
    def flaky_action():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise sqlite3.OperationalError("database is locked")
        return "recovered"

    res = execute_with_retry(flaky_action, max_retries=5, backoff_seconds=0.01)
    assert res == "recovered"
    assert call_count == 3
