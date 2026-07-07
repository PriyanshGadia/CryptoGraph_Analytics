import time
import os
import json
from functools import wraps
from typing import Any, Callable
from cachetools import TTLCache

# Try to initialize Redis
redis_client = None
redis_url = os.getenv("REDIS_URL")
if redis_url:
    try:
        import redis
        redis_client = redis.from_url(redis_url, decode_responses=True)
        redis_client.ping()
        print("[Cache] Connected to Redis for shared caching.")
    except Exception as e:
        print(f"[Cache] Redis connection failed: {e}. Falling back to in-memory TTLCache.")
        redis_client = None

# Fallback in-memory cache
_cache = TTLCache(maxsize=100, ttl=300)

def cached(ttl_seconds: int = 60):
    """Simple TTL cache for API responses. Uses Redis if available, else local TTLCache."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key safely, omitting DB session objects
            cache_kwargs = {k: v for k, v in kwargs.items() if k != "db" and not hasattr(v, "__session__")}
            safe_args = [arg for arg in args if not hasattr(arg, "__session__")]
            
            try:
                args_str = json.dumps(safe_args, sort_keys=True, default=str)
                kwargs_str = json.dumps(cache_kwargs, sort_keys=True, default=str)
            except Exception:
                args_str = str(safe_args)
                kwargs_str = str(cache_kwargs)
                
            key = f"cryptograph:{func.__name__}:{args_str}:{kwargs_str}"
            
            if redis_client:
                try:
                    cached_val = redis_client.get(key)
                    if cached_val:
                        return json.loads(cached_val)
                except Exception:
                    pass
            else:
                now = time.time()
                if key in _cache:
                    value, expires = _cache[key]
                    if now < expires:
                        return value

            result = func(*args, **kwargs)
            
            if redis_client:
                try:
                    redis_client.setex(key, ttl_seconds, json.dumps(result))
                except Exception:
                    pass
            else:
                _cache[key] = (result, time.time() + ttl_seconds)
                
            return result
        return wrapper
    return decorator
