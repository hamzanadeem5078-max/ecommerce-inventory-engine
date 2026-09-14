import time
import logging
from contextlib import asynccontextmanager
from typing import Tuple
from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis
from redis.exceptions import LockError, ResponseError, RedisError

import redis_db
from lua_engine import LuaScriptEngine
from redis_db import get_redis_client

logger = logging.getLogger(__name__)

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

    try:
        current_requests = await r_client.incr(redis_key)

        if current_requests == 1:
            await r_client.expire(redis_key, window)

        if current_requests > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please slow down your requests.",
            )
        yield
    except ResponseError as exc:
        if "OOM" in str(exc):
            logger.critical(f"CRITICAL: Redis Out-Of-Memory limit reached in guard: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="System under high memory pressure. Operation throttled.",
            )
        raise exc


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

    except Exception as exc:
        logger.warning(f"Failed to fetch dynamic tier rules for '{tier}', using fallback: {exc}")
        return fallback["limit"], fallback["window"]


async def enforce_rate_limit(request: Request):
    """
    FastAPI dependency enforcing static sliding window rate limiting per client IP.
    Legacy single-tier route guard.
    """
    client_ip = request.client.host if request.client else "unknown"

    try:
        redis_client = get_redis_client()
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
    except ResponseError as exc:
        if "OOM" in str(exc):
            logger.critical(f"CRITICAL: Redis Out-Of-Memory during static rate limit check: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Engine memory saturated. Request dropped for downstream protection.",
            )
        raise


async def enforce_dynamic_rate_limit(request: Request):
    """
    FastAPI dependency guarding routes with dynamic multi-tier rate limits.
    Executes atomic sliding window check via LuaScriptEngine with live Redis rules.
    Fails closed on Redis OOM/Connection errors to protect PostgreSQL.
    """
    rate_key, tier = await get_actor_tier_and_key(request)

    try:
        redis_client = get_redis_client()
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
    except ResponseError as exc:
        if "OOM" in str(exc):
            logger.critical(f"CRITICAL: Redis OOM in enforce_dynamic_rate_limit for key {rate_key}: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory boundary exceeded. Rate limit engine temporarily constrained.",
            )
        logger.error(f"Redis ResponseError in rate limiter: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Rate limiting engine evaluation error.",
        )
    except RedisError as exc:
        logger.error(f"Redis Connection failure during dynamic rate limit check: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable. Please retry shortly.",
        )