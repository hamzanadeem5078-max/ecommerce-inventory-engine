import logging
from contextvars import ContextVar
from contextlib import asynccontextmanager
from fastapi import Request
import redis.asyncio as aioredis
import redis_db

logger = logging.getLogger(__name__)

# Async-safe context variable for request correlation tracking
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="no-correlation-id")

@asynccontextmanager
async def rate_limit_guard(key: str, limit: int, window: int, client: aioredis.Redis):
    """Distributed sliding/fixed window rate limiter guard using Redis."""
    try:
        current_requests = await client.incr(key)
        if current_requests == 1:
            await client.expire(key, window)
        
        if current_requests > limit:
            logger.warning(f"[RATE LIMIT EXCEEDED] Key '{key}' reached {current_requests}/{limit} requests.")
            raise Exception("Rate limit exceeded. Please try again later.")
        
        yield
    except Exception as e:
        if "Rate limit exceeded" in str(e):
            raise e
        logger.error(f"[RATE LIMIT ERROR] Redis connection error during guard guard: {e}")
        yield

async def enforce_rate_limit(request: Request, limit: int = 60, window: int = 60):
    """FastAPI dependency for router-level rate limiting."""
    client_ip = request.client.host if request.client else "anonymous"
    client = redis_db.get_redis_client()
    async with rate_limit_guard(key=f"ratelimit:{client_ip}", limit=limit, window=window, client=client):
        yield

@asynccontextmanager
async def redis_lock_guard(lock_key: str, expire_sec: int = 5):
    """Distributed lock guard using Redis SETNX / Lua for flash sale inventory concurrency."""
    client = redis_db.get_redis_client()
    acquired = await client.set(lock_key, "locked", nx=True, ex=expire_sec)
    if not acquired:
        raise Exception("Concurrency conflict: Resource is currently locked. Try again.")
    try:
        yield
    finally:
        await client.delete(lock_key)