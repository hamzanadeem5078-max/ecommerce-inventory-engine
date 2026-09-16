import asyncio
import logging
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionLocal
from models import ProcessedEvent, OutboxEvent, OutboxStatus
from services import STREAM_NAME
from circuit_breaker import CircuitBreaker, CircuitState
import redis.asyncio as aioredis  # Async Redis client for pipeline execution

logger = logging.getLogger("worker")

GROUP_NAME = "inventory_workers"
CONSUMER_NAME = "worker_1"

# Instantiate circuit breaker protecting Redis Stream producers
redis_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)


async def setup_consumer_group(redis_client):
    try:
        await redis_client.xgroup_create(
            name=STREAM_NAME, groupname=GROUP_NAME, id="0", mkstream=True
        )
        logger.info(f"Consumer group '{GROUP_NAME}' initialized for '{STREAM_NAME}'")
    except Exception as e:
        if "BUSYGROUP" in str(e):
            pass
        else:
            raise e


async def parse_and_process_event(event_id: str, fields: dict):
    # Extract event_type from Redis Stream payload (default to ORDER_CREATED if absent)
    event_type = fields.get("event_type", "ORDER_CREATED")

    with SessionLocal() as session:
        # Idempotency Check
        stmt = select(ProcessedEvent).where(ProcessedEvent.event_id == event_id)
        existing = session.execute(stmt).scalar_one_or_none()

        if existing:
            logger.info(f"[IDEMPOTENT] Event {event_id} already processed. Skipping.")
            return

        # Persist event record matching exact ProcessedEvent schema (event_id, event_type)
        record = ProcessedEvent(
            event_id=event_id,
            event_type=event_type
        )
        session.add(record)
        session.commit()
        logger.info(f"[DB PERSISTED] Event {event_id} written to ledger.")


async def process_outbox_batch(db: AsyncSession, redis_client: aioredis.Redis, batch_size: int = 50):
    """
    Polls pending outbox events using row-level locks (FOR UPDATE SKIP LOCKED) 
    and dispatches them efficiently via Redis pipelines, protected by a circuit breaker.
    """
    # 1. Fail fast if circuit breaker is OPEN
    if redis_circuit_breaker.state == CircuitState.OPEN:
        logger.warning("[CIRCUIT BREAKER OPEN] Redis batch dispatch aborted. Preserving system resources.")
        return 0

    try:
        async with db.begin():
            stmt = (
                select(OutboxEvent)
                .where(OutboxEvent.status == OutboxStatus.PENDING)
                .order_by(OutboxEvent.created_at.asc())
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            result = await db.execute(stmt)
            events = result.scalars().all()

            if not events:
                return 0

            # 2. Open an async Redis pipeline for batch packet transmission
            pipe = redis_client.pipeline()
            for event in events:
                event.status = OutboxStatus.PROCESSING
                payload_data = {
                    "event_id": str(event.id),
                    "event_type": str(event.event_type),
                    "payload": str(event.payload)
                }
                pipe.xadd(STREAM_NAME, payload_data)

            # Execute pipeline network socket transaction atomically
            await pipe.execute()

            # 3. Mark events as processed/dispatched in PostgreSQL
            for event in events:
                event.status = OutboxStatus.PROCESSED
                logger.info(f"[OUTBOX DISPATCHED] Event {event.id} dispatched via pipeline successfully.")

        # Notify circuit breaker of successful execution
        await redis_circuit_breaker._on_success()
        return len(events)

    except Exception as e:
        # Notify circuit breaker of failure
        await redis_circuit_breaker._on_failure()
        logger.error(f"[OUTBOX ERROR] Batch dispatch pipeline failed: {e}")
        raise


async def worker_loop(redis_client):
    while True:
        try:
            entries = await redis_client.xreadgroup(
                groupname=GROUP_NAME,
                consumername=CONSUMER_NAME,
                streams={STREAM_NAME: ">"},
                count=10,
                block=1000,
            )

            if not entries:
                await asyncio.sleep(0.1)
                continue

            for stream, messages in entries:
                for message_id, fields in messages:
                    await parse_and_process_event(message_id, fields)
                    await redis_client.xack(STREAM_NAME, GROUP_NAME, message_id)

        except asyncio.CancelledError:
            logger.info("Worker task received cancellation signal. Exiting.")
            break
        except Exception as e:
            logger.error(f"Error in worker loop: {e}")
            await asyncio.sleep(1)