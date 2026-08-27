from contextlib import contextmanager
from fastapi import HTTPException, status
from redis.exceptions import LockError
from redis_db import get_redis_client # Or your existing Redis import name


def get_product_lock(redis_client, product_id: int):
    lock_key = f"lock:product:{product_id}"
    return redis_client.lock(
        name=lock_key,
        timeout=5.0,          # TTL: Auto-release after 5s if worker crashes
        blocking_timeout=2.0  # Queue Limit: Wait up to 2s in line
    )


@contextmanager
def redis_lock_guard(product_id: int, redis_client):
    lock = get_product_lock(redis_client, product_id)
    try:
        with lock:
            # Yield control to the caller while holding the lock
            yield lock
    except LockError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="High traffic volume. Could not acquire lock, please try again."
        )