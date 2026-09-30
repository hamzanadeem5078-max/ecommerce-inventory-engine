import os
import asyncio
import redis.asyncio as aioredis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_redis_client: aioredis.Redis | None = None
_client_loop = None

def get_redis_client() -> aioredis.Redis:
    global _redis_client, _client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    # If loop changed (e.g., TestClient background thread loop), reset client cleanly
    if _redis_client is None or _client_loop != current_loop:
        _redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        _client_loop = current_loop

    return _redis_client

# Module-level __getattr__ to support legacy imports like `from redis_db import redis_client`
def __getattr__(name):
    if name == "redis_client":
        return get_redis_client()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")