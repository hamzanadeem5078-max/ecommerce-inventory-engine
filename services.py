"""
services.py - Domain Service Integration & Status Code Mapping
"""

from enum import IntEnum
import logging
from datetime import datetime, timezone
import redis.asyncio as aioredis
from fastapi import HTTPException, status
from lua_engine import LuaScriptEngine
from lua_scripts import RESERVE_STOCK_LUA, ROLLBACK_STOCK_LUA
from schemas import OrderCreatedEvent

logger = logging.getLogger(__name__)

STREAM_NAME = "stream:order_events"
MAX_STREAM_LEN = 10000


class ReservationResult(IntEnum):
    SUCCESS = 1
    INSUFFICIENT_STOCK = 0
    ITEM_NOT_FOUND = -1
    ALREADY_CLAIMED = -2


class InventoryReservationService:
    """Encapsulates Lua execution logic behind domain abstractions and HTTP exceptions."""

    def __init__(self, script_engine: LuaScriptEngine):
        self.engine = script_engine
        self.script_body = RESERVE_STOCK_LUA
        self.rollback_script_body = ROLLBACK_STOCK_LUA

    async def reserve_flash_sale_item(
        self, item_id: str, user_id: str, quantity: int = 1
    ) -> bool:
        stock_key = f"flash_sale:stock:{item_id}"
        claims_key = f"flash_sale:claims:{item_id}"

        # Step 1: Execute Atomic Lua Reservation
        raw_result = await self.engine.execute_reservation(
            stock_key=stock_key,
            user_claims_key=claims_key,
            quantity=quantity,
            user_id=user_id,
            script_body=self.script_body,
        )

        result = ReservationResult(raw_result)

        if result != ReservationResult.SUCCESS:
            if result == ReservationResult.ALREADY_CLAIMED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="User has already claimed an item in this flash sale.",
                )

            if result == ReservationResult.INSUFFICIENT_STOCK:
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="Item is out of stock.",
                )

            if result == ReservationResult.ITEM_NOT_FOUND:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Flash sale item is not active or missing.",
                )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unhandled inventory reservation status.",
            )

        # Step 2: Validate Payload via Schema Contract
        event_payload = OrderCreatedEvent(
            item_id=item_id,
            user_id=user_id,
            quantity=quantity,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Step 3: Emit Event to Stream with Compensating Rollback Boundary
        try:
            await self.engine.redis_client.xadd(
                name=STREAM_NAME,
                fields=event_payload.model_dump(),
                maxlen=MAX_STREAM_LEN,
                approximate=True,
            )
        except aioredis.RedisError as exc:
            logger.error(
                f"XADD failed for item {item_id}, user {user_id}: {exc}. Triggering compensating rollback."
            )

            # Compensating Action: Restore Redis stock and remove user claim to prevent Phantom Reservation
            await self.engine.execute_rollback(
                stock_key=stock_key,
                user_claims_key=claims_key,
                quantity=quantity,
                user_id=user_id,
                script_body=self.rollback_script_body,
            )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Reservation pipeline failed at event stream emission stage. Stock state rolled back.",
            ) from exc

        return True