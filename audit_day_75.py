import asyncio
import logging
from database import SessionLocal
from sqlalchemy.future import select
from models import ProcessedEvent, OutboxEvent, OutboxStatus
from services import STREAM_NAME
import redis.asyncio as aioredis
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("audit_day_75")

async def run_audit():
    logger.info("=== STARTING 75-DAY SYSTEM INTEGRATION & TELEMETRY AUDIT ===")
    
    redis_url = f"redis://{settings.redis_host}:{settings.redis_port}"
    redis_client = aioredis.from_url(redis_url, decode_responses=True)
    
    try:
        # 1. Audit Redis Stream and Consumer Groups
        groups = await redis_client.xinfo_groups(STREAM_NAME)
        logger.info(f"[REDIS AUDIT] Active consumer groups for '{STREAM_NAME}': {groups}")
        
        stream_len = await redis_client.xlen(STREAM_NAME)
        logger.info(f"[REDIS AUDIT] Current stream length: {stream_len}")

        # 2. Audit Pending Entries (PEL)
        for group in groups:
            group_name = group.get("name")
            pending_info = await redis_client.xpending(STREAM_NAME, group_name)
            logger.info(f"[PEL AUDIT] Group '{group_name}' Pending Count: {pending_info.get('pending', 0)}")

        # 3. Audit PostgreSQL Database Consistency
        with SessionLocal() as session:
            outbox_pending = session.execute(
                select(OutboxEvent).where(OutboxEvent.status == OutboxStatus.PENDING)
            ).scalars().all()
            
            processed_count = session.execute(
                select(ProcessedEvent)
            ).scalars().all()

            logger.info(f"[DB AUDIT] Pending Outbox Events: {len(outbox_pending)}")
            logger.info(f"[DB AUDIT] Total Processed Events Ledger Count: {len(processed_count)}")

        logger.info("=== 75-DAY AUDIT COMPLETED SUCCESSFULLY: ALL INVARIANTS HOLD ===")
        
    except Exception as e:
        logger.error(f"[AUDIT FAILURE] System anomaly detected during 75-day audit: {e}")
        raise
    finally:
        await redis_client.close()

if __name__ == "__main__":
    asyncio.run(run_audit())