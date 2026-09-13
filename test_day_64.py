import asyncio
from fastapi import HTTPException, Request
from dependencies import enforce_dynamic_rate_limit, DEFAULT_TIER_RULES, get_actor_tier_and_key
from redis_db import get_redis_client

class DummyClient:
    host = "127.0.0.1"

class DummyRequest:
    def __init__(self):
        self.client = DummyClient()
        self.state = type("State", (), {})()

async def run_verification():
    redis = await get_redis_client()
    req = DummyRequest()
    
    # 1. Resolve raw identifier and derive the exact Redis key constructed by LuaScriptEngine
    raw_key, tier = await get_actor_tier_and_key(req)
    actual_redis_key = f"rate_limit:{raw_key}"

    # Clear any previous test artifacts
    await redis.delete(actual_redis_key)

    anon_limit = DEFAULT_TIER_RULES["anonymous"]["limit"]

    print(f"--- TESTING DYNAMIC SLIDING WINDOW (Limit: {anon_limit}) ---")
    print(f"Targeting Redis Key: '{actual_redis_key}'")

    # 2. Burst requests up to allowable limit
    for i in range(1, anon_limit + 1):
        await enforce_dynamic_rate_limit(req)
        print(f"Request {i}/{anon_limit}: ALLOWED")

    # 3. Next request MUST throw HTTP 429
    try:
        await enforce_dynamic_rate_limit(req)
        print("FAIL: Request exceeded limit but was ALLOWED")
    except HTTPException as e:
        print(f"Request {anon_limit + 1}: BLOCKED -> HTTP {e.status_code}")
        print(f"Response Detail: {e.detail}")

    # 4. Verify ZSET cardinality strictly equals anon_limit
    cardinality = await redis.zcard(actual_redis_key)
    print(f"ZSET Cardinality for '{actual_redis_key}': {cardinality} (Expected: {anon_limit})")

    # 5. Cleanup test artifacts
    await redis.delete(actual_redis_key)

if __name__ == "__main__":
    asyncio.run(run_verification())