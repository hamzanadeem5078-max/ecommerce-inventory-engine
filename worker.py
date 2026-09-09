import asyncio
import logging
from sqlalchemy.future import select

from database import SessionLocal
from models import ProcessedEvent
from services import STREAM_NAME

logger = logging.getLogger("worker")

GROUP_NAME = "inventory_workers"
CONSUMER_NAME = "worker_1"


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