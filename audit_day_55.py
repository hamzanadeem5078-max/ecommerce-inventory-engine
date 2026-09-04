import asyncio
import json
import logging
import database
from redis_db import get_redis_client
import worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("AuditDay55")

STREAM_NAME = worker.STREAM_KEY
GROUP_NAME = worker.GROUP_NAME
DLQ_STREAM = worker.DLQ_STREAM_KEY

async def run_audit():
    logger.info("Starting Day 55 Integration Audit...")
    redis = await get_redis_client()

    # Flush state for clean test run
    await redis.delete(STREAM_NAME, DLQ_STREAM)
    
    # Initialize Consumer Group
    await worker.setup_consumer_group(redis)

    # =========================================================================
    # BLOCK 1: Testing Poison Pill Interception
    # =========================================================================
    logger.info("=== BLOCK 1: Testing Poison Pill Interception ===")
    
    # Inject malformed payload
    poison_msg_id = await redis.xadd(STREAM_NAME, {"payload": "invalid_json_str{"})
    logger.info(f"Injected Poison Pill directly into Stream ID: {poison_msg_id}")

    # Read and attempt parse/process
    messages = await redis.xreadgroup(
        groupname=GROUP_NAME,
        consumername="audit_worker_1",
        streams={STREAM_NAME: ">"},
        count=1
    )
    for stream_name, msg_list in messages:
        for msg_id, msg_data in msg_list:
            str_id = msg_id.decode("utf-8") if isinstance(msg_id, bytes) else msg_id
            await worker.parse_and_process_event(str_id, msg_data, redis)

    # Check that main PEL is empty for this message
    pel_info = await redis.xpending(STREAM_NAME, GROUP_NAME)
    assert pel_info["pending"] == 0, "Poison pill was not acknowledged out of PEL!"
    logger.info(f"✓ PASS: Poison message {poison_msg_id} was intercepted and XACKed out of active PEL.")

    # =========================================================================
    # BLOCK 2: Simulating Worker Crash & PEL Orphanage
    # =========================================================================
    logger.info("=== BLOCK 2: Simulating Worker Crash & PEL Orphanage ===")

    valid_payload = json.dumps({"order_id": "ORD-9999", "item": "Flash Item", "qty": 1})
    valid_msg_id = await redis.xadd(STREAM_NAME, {"payload": valid_payload})
    logger.info(f"Injected Valid Event Stream ID: {valid_msg_id}")

    # Simulate crash: Read message into PEL as 'worker_node_1' without calling XACK
    crashed_read = await redis.xreadgroup(
        groupname=GROUP_NAME,
        consumername="worker_node_1",
        streams={STREAM_NAME: ">"},
        count=1
    )
    assert len(crashed_read) > 0, "Failed to read event into worker PEL!"
    logger.info(f"Simulated crash: worker_node_1 read message {valid_msg_id} into PEL without sending XACK.")

    # Verify raw message existence in PEL immediately
    pel_info = await redis.xpending(STREAM_NAME, GROUP_NAME)
    assert pel_info["pending"] > 0, "Failed to verify orphaned status in Pending Entries List!"
    logger.info(f"✓ PASS: Message {valid_msg_id} confirmed stuck in PEL under worker_node_1.")

    # =========================================================================
    # BLOCK 3: Executing Claim & Recovery
    # =========================================================================
    logger.info("=== BLOCK 3: Executing Claim & Recovery ===")

    # Temporarily lower recovery idle time threshold for instant test recovery
    original_idle = worker.MIN_IDLE_TIME_MS
    worker.MIN_IDLE_TIME_MS = 0

    try:
        await worker.process_recovered_events(
            redis_client=redis,
            db_session_factory=database.SessionLocal,
            stream_key=STREAM_NAME,
            group_name=GROUP_NAME,
            consumer_name="recovery_worker_2"
        )
    finally:
        worker.MIN_IDLE_TIME_MS = original_idle

    # Verify PEL is now completely cleared
    final_pel = await redis.xpending(STREAM_NAME, GROUP_NAME)
    assert final_pel["pending"] == 0, f"Expected 0 pending messages in PEL, found {final_pel['pending']}"
    logger.info(f"✓ PASS: Orphaned message {valid_msg_id} was claimed, processed, and acknowledged by recovery_worker_2.")

    logger.info("=========================================================")
    logger.info("🎉 DAY 55 INTEGRATION AUDIT PASSED 100% SUCCESSFULLY 🎉")
    logger.info("=========================================================")

if __name__ == "__main__":
    asyncio.run(run_audit())