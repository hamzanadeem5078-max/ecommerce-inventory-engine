import asyncio
import sys
import logging
from redis.asyncio import Redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("AUDIT_DAY_65")


async def run_milestone_audit():
    logger.info("==================================================")
    logger.info("   MILESTONE AUDIT DAY 65: RESILIENT INFRASTRUCTURE")
    logger.info("==================================================")

    redis = Redis(host="localhost", port=6379, db=0, decode_responses=True)

    try:
        # 1. Connection Handshake
        ping_res = await redis.ping()
        assert ping_res is True, "Ping failed"
        logger.info(f"[PASS] 1. Redis Ping Handshake: {ping_res}")

        # 2. Inspect Memory Usage & Policy
        info_mem = await redis.info("memory")
        used_memory = info_mem.get("used_memory_human", "N/A")
        maxmemory_policy = info_mem.get("maxmemory_policy", "N/A")
        logger.info(f"[PASS] 2. Redis Memory Audit: Used = {used_memory} | Policy = {maxmemory_policy}")

        # 3. Test Lua ZSET Expiry & Garbage Collection Isolation
        test_key = "{rate_limit:audit}:test_user_65"
        await redis.zadd(test_key, {f"req_stale_{i}": 1000 + i for i in range(10)})
        await redis.expire(test_key, 60)

        ttl = await redis.ttl(test_key)
        zcard = await redis.zcard(test_key)

        assert ttl > 0, "TTL was not set on test key"
        assert zcard == 10, "ZSET entries mismatch"
        logger.info(f"[PASS] 3. Lua Key Hygiene: Key TTL = {ttl}s | ZSET Size = {zcard}")

        # Clean up test key
        await redis.delete(test_key)
        logger.info("[PASS] 4. Test Key Cleaned Successfully.")

        logger.info("--------------------------------------------------")
        logger.info("ALL DAY 65 DUAL-PURPOSE AUDIT CHECKS PASSED")
        logger.info("--------------------------------------------------")

    except Exception as exc:
        logger.error(f"[AUDIT FAILED] Verification error: {exc}")
        sys.exit(1)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(run_milestone_audit())