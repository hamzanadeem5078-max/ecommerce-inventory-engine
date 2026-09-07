"""
services.py - Domain Service Integration & Status Code Mapping
"""

from enum import IntEnum
from fastapi import HTTPException, status
from lua_engine import LuaScriptEngine
from lua_scripts import RESERVE_STOCK_LUA


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

    async def reserve_flash_sale_item(
        self, item_id: str, user_id: str, quantity: int = 1
    ) -> bool:
        stock_key = f"flash_sale:stock:{item_id}"
        claims_key = f"flash_sale:claims:{item_id}"

        raw_result = await self.engine.execute_reservation(
            stock_key=stock_key,
            user_claims_key=claims_key,
            quantity=quantity,
            user_id=user_id,
            script_body=self.script_body,
        )

        result = ReservationResult(raw_result)

        if result == ReservationResult.SUCCESS:
            return True

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