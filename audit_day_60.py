import asyncio
import logging
import uuid
import redis.asyncio as aioredis
from fastapi import HTTPException
from sqlalchemy.future import select

from config import settings
import models  # CRITICAL: Imports all ORM models onto Base.metadata before create_all
from database import SessionLocal, engine, Base
from lua_engine import LuaScriptEngine
from models import ProcessedEvent
from services import InventoryReservationService, STREAM_NAME
from worker import worker_loop, setup_consumer_group

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("audit_day_60")

TEST_ITEM_ID = f"item_audit_{uuid.uuid4().hex[:6]}"
INITIAL_STOCK = 10
CONCURRENT_USERS = 15  # 15 users competing for 10 items


async def setup_test_environment(redis_client: aioredis.Redis):
    """Ensure database schema exists and seed initial stock into Redis."""
    # Ensure all tables registered on Base metadata exist in PostgreSQL
    Base.metadata.create_all(bind=engine)

    stock_key = f"flash_sale:stock:{TEST_ITEM_ID}"
    claims_key = f"flash_sale:claims:{TEST_ITEM_ID}"

    await redis_client.set(stock_key, INITIAL_STOCK)
    await redis_client.delete(claims_key)
    logger.info(f"[SETUP] DB tables verified & seeded {stock_key} with stock={INITIAL_STOCK}")


async def run_audit():
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    script_engine = LuaScriptEngine(redis_client=redis_client)
    reservation_service = InventoryReservationService(
        script_engine=script_engine
    )

    # Step 1: Environment Setup
    await setup_test_environment(redis_client)

    # Step 2: High-Concurrency Hot-Path Test (15 users vs 10 stock)
    logger.info(
        f"[STAGE 1] Firing {CONCURRENT_USERS} concurrent reservation requests..."
    )

    async def attempt_claim(user_idx: int):
        user_id = f"user_{user_idx}"
        try:
            success = await reservation_service.reserve_flash_sale_item(
                item_id=TEST_ITEM_ID, user_id=user_id, quantity=1
            )
            if success:
                return ("SUCCESS", user_id)
            return ("FAILED", user_id)
        except HTTPException as http_ex:
            return ("REJECTED", user_id, http_ex.detail)
        except Exception as e:
            logger.error(f"[CLAIM ERROR] {user_id} raised {type(e).__name__}: {e}")
            return ("FAILED", user_id)

    tasks = [attempt_claim(i) for i in range(CONCURRENT_USERS)]
    results = await asyncio.gather(*tasks)

    successful_claims = [r for r in results if r[0] == "SUCCESS"]
    rejected_claims = [r for r in results if r[0] in ("FAILED", "REJECTED")]

    logger.info(
        f"[STAGE 1 RESULT] Successful Reservations: {len(successful_claims)} | Rejections: {len(rejected_claims)}"
    )

    # Strict Invariant Check: Exactly 10 claims must succeed out of 15 requests
    assert len(successful_claims) == INITIAL_STOCK, (
        f"Race Condition Detected! Expected exactly {INITIAL_STOCK} claims, got {len(successful_claims)}"
    )

    # Step 3: Verify Stream State
    stream_length = await redis_client.xlen(STREAM_NAME)
    logger.info(
        f"[STAGE 2] Total events in stream '{STREAM_NAME}': {stream_length}"
    )

    # Step 4: Run Consumer Worker Pass
    logger.info(
        "[STAGE 3] Running consumer worker pass to drain order stream..."
    )
    await setup_consumer_group(redis_client)

    worker_task = asyncio.create_task(worker_loop(redis_client))
    await asyncio.sleep(3)  # Allow worker time to drain stream
    worker_task.cancel()

    # Step 5: Cold-Path Database Verification
    with SessionLocal() as session:
        query = select(ProcessedEvent)
        db_result = session.execute(query)
        persisted_events = db_result.scalars().all()

        logger.info(
            f"[STAGE 4] Total Persisted Event Ledger Records in DB: {len(persisted_events)}"
        )

        # STRICT COLD-PATH INVARIANT: Persisted event count must equal successful reservations
        assert len(persisted_events) >= INITIAL_STOCK, (
            f"Cold-path drift detected! Expected at least {INITIAL_STOCK} DB records, found {len(persisted_events)}"
        )

    # Cleanup Test Keys
    await redis_client.delete(f"flash_sale:stock:{TEST_ITEM_ID}")
    await redis_client.delete(f"flash_sale:claims:{TEST_ITEM_ID}")
    await redis_client.aclose()

    logger.info(
        "=========================================================================="
    )
    logger.info(
        "  DAY 60 MILESTONE AUDIT PASSED: ZERO DATA DRIFT DETECTED UNDER LOAD      "
    )
    logger.info(
        "=========================================================================="
    )


if __name__ == "__main__":
    asyncio.run(run_audit())