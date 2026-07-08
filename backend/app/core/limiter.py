import os
from slowapi import Limiter
from slowapi.util import get_remote_address

# Zero-cost rate limiting bypass during unit/integration tests to prevent flaky failures
is_testing = os.getenv("TESTING") == "True"

limiter = Limiter(
    key_func=get_remote_address,
    enabled=not is_testing,
    default_limits=["120/minute", "5/second"]
)
