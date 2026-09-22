import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select
from models import OutboxEvent, OutboxStatus
from database import SessionLocal
from metrics import replay_counter

router = APIRouter(prefix="/dlq", tags=["Dead Letter Queue"])
logger = logging.getLogger("uvicorn.error")

async def get_db_session():
    async with SessionLocal() as session:
        yield session

@router.get("/events", status_code=status.HTTP_200_OK)
async def inspect_dead_outbox_events(
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session)
):
    """Bounded inspection of dead/quarantined outbox events."""
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.status == OutboxStatus.DEAD)
        .limit(limit)
    )
    result = await db.execute(stmt)
    events = result.scalars().all()
    return {
        "count": len(events),
        "limit": limit,
        "events": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "payload": e.payload,
                "retry_count": str(e.retry_count),
                "last_error": e.last_error
            }
            for e in events
        ]
    }

@router.post("/events/{event_id}/replay", status_code=status.HTTP_200_OK)
async def replay_dead_event(event_id: uuid.UUID, db: AsyncSession = Depends(get_db_session)):
    """Safe atomic state transition from DEAD back to PENDING for reprocessing."""
    async with db.begin():
        stmt = (
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id, OutboxEvent.status == OutboxStatus.DEAD)
            .values(
                status=OutboxStatus.PENDING,
                retry_count="0",
                last_error=None,
                failed_at=None
            )
            .returning(OutboxEvent.id)
        )
        result = await db.execute(stmt)
        updated_id = result.scalar_one_or_none()
        
        if not updated_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dead event {event_id} not found or not in 'DEAD' state."
            )
            
    replay_counter.labels(queue_name="outbox_db_dlq", status="replayed").inc()
    logger.info(f"[DLQ REPLAY] Event {updated_id} reset to PENDING state (retry_count reset to '0').")
    return {"status": "replayed", "event_id": str(updated_id)}