import time
from contextlib import asynccontextmanager
from fastapi import HTTPException, status
from redis.exceptions import LockError
import redis_db


def get_product_lock(product_id: int, client=None):
    r_client = client or redis_db.redis_client
    lock_key = f"lock:product:{product_id}"
    return r_client.lock(
        name=lock_key,
        timeout=5.0,  # TTL: Auto-release after 5s if worker crashes
        blocking_timeout=2.0,  # Queue Limit: Wait up to 2s in line
    )


@asynccontextmanager
async def redis_lock_guard(product_id: int, client=None):
    lock = get_product_lock(product_id, client=client)
    try:
        async with lock:
            # Yield control to the caller while holding the lock
            yield lock
    except LockError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="High traffic volume. Could not acquire lock, please try again.",
        )


@asynccontextmanager
async def rate_limit_guard(
    key: str, limit: int = 10, window: int = 60, client=None
):
    """Async Fixed-window rate limiter using Redis."""
    r_client = client or redis_db.redis_client
    current_time = int(time.time())
    redis_key = f"rate_limit:{key}:{current_time // window}"

    current_requests = await r_client.incr(redis_key)

    # Set expiration on the key when created
    if current_requests == 1:
        await r_client.expire(redis_key, window)

    if current_requests > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please slow down your requests.",
        )

    try:
        yield
    finally:
        pass