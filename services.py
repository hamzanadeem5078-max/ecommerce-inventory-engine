import json
import logging
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
from lua_engine import LuaScriptEngine
from models import OutboxEvent, OutboxStatus
from schemas import DLQInspectResponse, DLQMessageSchema

logger = logging.getLogger("services")

STREAM_NAME = "stream:order_events"
DLQ_STREAM_NAME = "dlq:events"


class InventoryReservationService:
    def __init__(self, script_engine: LuaScriptEngine):
        self.script_engine = script_engine

    async def reserve_flash_sale_item(self, item_id: str, user_id: str, quantity: int = 1) -> bool:
        stock_key = f"flash_sale:stock:{item_id}"
        claims_key = f"flash_sale:claims:{item_id}"

        # Execute atomic Lua reservation
        result_code = await self.script_engine.reserve_stock(
            stock_key=stock_key,
            claims_key=claims_key,
            user_id=user_id,
            quantity=quantity
        )

        if result_code == -1:
            raise HTTPException(status_code=400, detail="User already claimed this item.")
        elif result_code == 0:
            raise HTTPException(status_code=410, detail="Item is out of stock.")
        elif result_code == 1:
            # Publish event to Stream for cold-path persistence
            await self.script_engine.redis_client.xadd(
                STREAM_NAME,
                {
                    "user_id": str(user_id),
                    "item_id": str(item_id),
                    "quantity": str(quantity),
                }
            )
            return True

        return False

    async def reserve_flash_sale_item_with_outbox(
        self, 
        db: AsyncSession, 
        item_id: str, 
        user_id: str, 
        quantity: int = 1
    ) -> bool:
        """
        Reserves stock via Redis Lua and guarantees atomic 
        outbox event creation within a PostgreSQL transaction boundary.
        """
        try:
            stock_key = f"flash_sale:stock:{item_id}"
            claims_key = f"flash_sale:claims:{item_id}"

            # 1. Execute atomic Lua reservation
            result_code = await self.script_engine.reserve_stock(
                stock_key=stock_key,
                claims_key=claims_key,
                user_id=user_id,
                quantity=quantity
            )

            if result_code == -1:
                raise HTTPException(status_code=400, detail="User already claimed this item.")
            elif result_code == 0:
                raise HTTPException(status_code=410, detail="Item is out of stock.")
            
            if result_code == 1:
                # 2. Instantiate and stage Outbox Event in the same DB session
                outbox_event = OutboxEvent(
                    event_type="INVENTORY_RESERVED",
                    payload={
                        "user_id": str(user_id),
                        "item_id": str(item_id),
                        "quantity": str(quantity),
                    },
                    status=OutboxStatus.PENDING
                )
                db.add(outbox_event)
                
                # 3. Atomic Commit: DB state change + Outbox record commit together
                await db.commit()
                await db.refresh(outbox_event)
                
                logger.info(f"Inventory reserved & outbox event {outbox_event.id} committed.")
                return True

            return False

        except Exception as e:
            await db.rollback()
            logger.error(f"Transaction failed for item {item_id}, rolling back. Error: {e}")
            raise


async def read_dlq_bounded(
    redis: aioredis.Redis, 
    stream_key: str = DLQ_STREAM_NAME, 
    limit: int = 50, 
    max_hard_cap: int = 100
) -> DLQInspectResponse:
    safe_limit = min(max(1, limit), max_hard_cap)
    # Newest-first inspection for quarantine triage
    raw_messages = await redis.xrevrange(stream_key, max="+", min="-", count=safe_limit)
    
    parsed = [
        DLQMessageSchema.from_redis_tuple(msg_id, fields)
        for msg_id, fields in raw_messages
    ]
    return DLQInspectResponse(
        stream_key=stream_key,
        limit=safe_limit,
        count=len(parsed),
        messages=parsed
    )


class DLQReplayService:
    """
    Day 72: Safe Administrative Re-injection & Replay Service with Idempotency Guard.
    """
    def __init__(
        self, 
        redis_client: aioredis.Redis, 
        target_stream: str = STREAM_NAME, 
        dlq_stream: str = DLQ_STREAM_NAME
    ):
        self.redis = redis_client
        self.target_stream = target_stream
        self.dlq_stream = dlq_stream

    async def replay_message(self, message_id: str, idempotency_ttl: int = 86400) -> dict:
        idempotency_key = f"dlq:replayed:{message_id}"
        
        # 1. Acquire Idempotency Guard (NX = Set only if not exists, TTL prevents key leakage)
        acquired = await self.redis.set(idempotency_key, "1", ex=idempotency_ttl, nx=True)
        if not acquired:
            logger.info(f"[DLQ Replay] Duplicate replay blocked for message {message_id}.")
            return {"status": "ALREADY_REPLAYED", "message_id": message_id}

        try:
            # 2. Fetch target DLQ message payload by exact ID lookup
            raw = await self.redis.xrange(self.dlq_stream, min=message_id, max=message_id)
            if not raw:
                # Release idempotency guard if record missing from quarantine stream
                await self.redis.delete(idempotency_key)
                raise HTTPException(status_code=404, detail=f"DLQ message {message_id} not found in {self.dlq_stream}")

            _, fields = raw[0]

            # 3. Mutate / Enrich metadata safely
            current_retries = 0
            try:
                current_retries = int(fields.get("retry_count", 0))
            except ValueError:
                current_retries = 0
            new_retries = current_retries + 1

            enriched_fields = dict(fields)
            enriched_fields["retry_count"] = str(new_retries)
            enriched_fields["replayed_at"] = datetime.now(timezone.utc).isoformat()
            # Strip previous failure artifacts if desired, or retain for telemetry

            # 4. Re-inject into active target stream
            new_target_id = await self.redis.xadd(self.target_stream, enriched_fields)

            # 5. Excise poison pill from DLQ quarantine stream ONLY post-verification
            await self.redis.xdel(self.dlq_stream, message_id)

            logger.info(
                f"[DLQ Replay] Successfully replayed {message_id} -> {new_target_id} "
                f"on {self.target_stream} (retry_count={new_retries})"
            )
            return {
                "status": "REPLAYED",
                "dlq_message_id": message_id,
                "target_message_id": new_target_id,
                "retry_count": new_retries
            }

        except Exception as e:
            # Rollback idempotency guard on failure so operator can retry after fixing root cause
            await self.redis.delete(idempotency_key)
            if isinstance(e, HTTPException):
                raise
            logger.error(f"[DLQ Replay] Failed replay execution for {message_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Replay execution failed: {str(e)}")