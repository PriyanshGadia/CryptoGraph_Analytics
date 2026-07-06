import time
from functools import wraps
from typing import Any, Callable
from cachetools import LRUCache

_cache = LRUCache(maxsize=1000)

def cached(ttl_seconds: int = 60):
    """Simple TTL cache for API responses."""
    def decorator(func: Callable):
        # We use a standard wrapper instead of async def since the endpoints are now synchronous
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key from function name + kwargs, omitting 'db' since it changes per request
            cache_kwargs = {k: v for k, v in kwargs.items() if k != "db"}
            key = f"{func.__name__}:{str(args)}:{str(cache_kwargs)}"
            
            now = time.time()
            if key in _cache:
                value, expires = _cache[key]
                if now < expires:
                    return value
                    
            result = func(*args, **kwargs)
            _cache[key] = (result, now + ttl_seconds)
            return result
        return wrapper
    return decorator
