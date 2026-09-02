import asyncio
import json
import logging
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import config
import database
import models
import schemas

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("BackgroundWorker")

# Stream Configuration
STREAM_KEY = "orders_stream"
GROUP_NAME = "inventory_workers"
CONSUMER_NAME = "worker_node_1"

# Loop Control Flag for Pause / Resume / Shutdown
is_running = asyncio.Event()
is_running.set()


async def setup_consumer_group(redis_client: Redis):
    """
    Ensures the Redis Stream and Consumer Group exist on startup.
    Idempotent: Catches BUSYGROUP error gracefully.
    """
    try:
        await redis_client.xgroup_create(
            name=STREAM_KEY, groupname=GROUP_NAME, id="0", mkstream=True
        )
        logger.info(f"Created Consumer Group: '{GROUP_NAME}' on stream '{STREAM_KEY}'")
    except ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.info(f"Consumer Group '{GROUP_NAME}' already exists. Skipping initialization.")
        else:
            logger.error(f"Failed to create Consumer Group: {e}")
            raise e


async def process_event_idempotently(envelope: schemas.EventEnvelopeSchema, order_event: schemas.OrderCreate) -> bool:
    """
    Executes deduplication check, records processed event ledger,
    and applies domain mutations inside a single atomic database transaction.
    """
    async with database.AsyncSessionLocal() as session:
        try:
            async with session.begin():  # Explicit atomic transaction boundary
                # 1. Deduplication Check
                stmt = select(models.ProcessedEvent).where(models.ProcessedEvent.event_id == envelope.event_id)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    logger.warning(f"[IDEMPOTENT SKIP] Duplicate event detected: {envelope.event_id}")
                    return True  # Idempotent hit: return True so caller dispatches XACK

                # 2. Record event in ProcessedEvent ledger
                processed_record = models.ProcessedEvent(
                    event_id=envelope.event_id,
                    event_type=envelope.event_type
                )
                session.add(processed_record)

                # 3. Domain Logic Execution (Example: Order record creation or inventory adjustments)
                logger.info(
                    f"[EXECUTING DOMAIN LOGIC] Event ID: {envelope.event_id} | "
                    f"Product ID: {order_event.product_id} | Qty: {order_event.quantity}"
                )

                return True  # Auto-commits clean state on exit of session.begin()

        except IntegrityError:
            # Race condition trap: Concurrent workers attempted writing same event_id simultaneously
            await session.rollback()
            logger.warning(f"[RACE CONDITION] Concurrent execution prevented for Event ID: {envelope.event_id}")
            return True

        except Exception as e:
            # System/DB outage: Roll back state completely so the worker retries
            await session.rollback()
            logger.error(f"[TRANSACTION FAILED] Could not process Event ID {envelope.event_id}: {e}")
            return False


async def parse_and_process_event(message_id: str, message_data: dict, redis_client: Redis):
    """
    Deserializes raw Redis Stream payload, validates boundaries, calls the idempotent DB handler,
    and dispatches XACK conditionally upon success.
    """
    try:
        # 1. Convert raw byte keys/values from Redis dictionary to strings
        decoded_data = {
            (k.decode("utf-8") if isinstance(k, bytes) else k): (
                v.decode("utf-8") if isinstance(v, bytes) else v
            )
            for k, v in message_data.items()
        }

        # Handle nested stringified payload inside EventEnvelopeSchema
        if "payload" in decoded_data and isinstance(decoded_data["payload"], str):
            decoded_data["payload"] = json.loads(decoded_data["payload"])

        # 2. Poison Pill Boundary: Parse through EventEnvelopeSchema
        envelope = schemas.EventEnvelopeSchema(**decoded_data)
        
        # 3. Extract and validate specific order payload
        order_event = schemas.OrderCreate(**envelope.payload)

        # 4. Atomic Idempotent Transaction Execution
        success = await process_event_idempotently(envelope, order_event)

        # 5. CONDITIONAL ACK INVARIANT: Send XACK strictly when state is committed or skipped
        if success:
            await redis_client.xack(STREAM_KEY, GROUP_NAME, message_id)
            logger.info(f"[ACK] Message ID {message_id} acknowledged.")
        else:
            logger.warning(f"[RETAIN] Message ID {message_id} un-ACKed. Retained in PEL for retry.")

    except (ValidationError, json.JSONDecodeError) as e:
        # Poison pill payload: ACK immediately so corrupt data doesn't block processing
        logger.error(f"[POISON PILL] Malformed payload in message {message_id}: {e}")
        await redis_client.xack(STREAM_KEY, GROUP_NAME, message_id)

    except Exception as e:
        # Unexpected loop/parsing error
        logger.error(f"[SYSTEM FAILURE] Unexpected error handling message {message_id}: {e}")


async def worker_loop(redis_client: Redis):
    """
    Continuous async loop polling Redis Streams using XREADGROUP.
    """
    await setup_consumer_group(redis_client)
    logger.info(f"Worker '{CONSUMER_NAME}' online. Polling '{STREAM_KEY}'...")

    while True:
        await is_running.wait()

        try:
            # block=2000 yields control back to asyncio event loop without pinning CPU
            response = await redis_client.xreadgroup(
                groupname=GROUP_NAME,
                consumername=CONSUMER_NAME,
                streams={STREAM_KEY: ">"},
                count=10,
                block=2000,
            )

            if not response:
                continue

            for stream_name, message_list in response:
                for message_id, message_data in message_list:
                    str_id = message_id.decode("utf-8") if isinstance(message_id, bytes) else message_id
                    await parse_and_process_event(str_id, message_data, redis_client)

        except Exception as e:
            logger.error(f"[LOOP ERROR] Unexpected error in worker loop: {e}")
            await asyncio.sleep(2)


async def main():
    """
    Process entrypoint with graceful shutdown signal handling.
    """
    redis_client = Redis.from_url(config.settings.REDIS_URL, decode_responses=False)

    try:
        await worker_loop(redis_client)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("[SHUTDOWN] Interruption signal received. Initiating graceful shutdown...")
    finally:
        is_running.clear()
        logger.info("[SHUTDOWN] Closing Redis connection pool...")
        await redis_client.close()
        logger.info("[SHUTDOWN] Worker process cleanly terminated.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass