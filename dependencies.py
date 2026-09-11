import time
from contextlib import asynccontextmanager
from typing import Tuple

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis
from redis.exceptions import LockError

import redis_db
from lua_engine import LuaScriptEngine
from redis_db import get_redis_client

# In-memory defensive contract (Fallback when Redis config is missing or unreachable)
DEFAULT_TIER_RULES = {
    "vip": {"limit": 100, "window": 60},
    "standard": {"limit": 20, "window": 60},
    "anonymous": {"limit": 5, "window": 60},
}


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


async def get_actor_tier_and_key(request: Request) -> Tuple[str, str]:
    """
    Extracts subject identifier and tier.
    Prioritizes authenticated user ID over client IP.
    """
    user_id = getattr(request.state, "user_id", None)
    user_tier = getattr(request.state, "user_tier", None)

    if user_id:
        tier = user_tier if user_tier in DEFAULT_TIER_RULES else "standard"
        return f"rate_limit:user:{user_id}", tier

    client_ip = request.client.host if request.client else "unknown"
    return f"rate_limit:ip:{client_ip}", "anonymous"


async def fetch_tier_rule(redis: Redis, tier: str) -> Tuple[int, int]:
    """
    Fetches dynamic tier rules from Redis Hash 'rate_limit:rules'.
    Falls back to DEFAULT_TIER_RULES on missing keys or Redis errors.
    """
    fallback = DEFAULT_TIER_RULES.get(tier, DEFAULT_TIER_RULES["anonymous"])

    try:
        rule_data = await redis.hmget(
            "rate_limit:rules", [f"{tier}:limit", f"{tier}:window"]
        )
        raw_limit, raw_window = rule_data[0], rule_data[1]

        limit = int(raw_limit) if raw_limit is not None else fallback["limit"]
        window = int(raw_window) if raw_window is not None else fallback["window"]
        return limit, window

    except Exception:
        # Prevent Redis connection failures from dropping traffic—fail open to defaults
        return fallback["limit"], fallback["window"]


async def enforce_rate_limit(request: Request):
    """
    FastAPI dependency enforcing static sliding window rate limiting per client IP.
    Legacy single-tier route guard.
    """
    client_ip = request.client.host if request.client else "unknown"

    redis_client = await get_redis_client()
    engine = LuaScriptEngine(redis_client)

    is_allowed = await engine.check_rate_limit(
        identifier=client_ip, max_limit=5, window_seconds=10
    )

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Flash sale checkout attempts throttled.",
            headers={"Retry-After": "10"},
        )


async def enforce_dynamic_rate_limit(request: Request):
    """
    FastAPI dependency guarding routes with dynamic multi-tier rate limits.
    Executes atomic sliding window check via LuaScriptEngine with live Redis rules.
    """
    rate_key, tier = await get_actor_tier_and_key(request)

    redis_client = await get_redis_client()
    max_limit, window_seconds = await fetch_tier_rule(redis_client, tier)

    engine = LuaScriptEngine(redis_client)
    is_allowed = await engine.check_rate_limit(
        identifier=rate_key,
        max_limit=max_limit,
        window_seconds=window_seconds,
    )

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Rate limit exceeded",
                "tier": tier,
                "limit": max_limit,
                "window_seconds": window_seconds,
            },
            headers={
                "Retry-After": str(window_seconds),
                "X-RateLimit-Limit": str(max_limit),
                "X-RateLimit-Remaining": "0",
            },
        )