import logging
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from lua_engine import LuaScriptEngine
from models import OutboxEvent, OutboxStatus

logger = logging.getLogger("services")

STREAM_NAME = "stream:order_events"


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