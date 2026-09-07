"""
lua_engine.py - SHA1 Pre-loading Manager and Fault-Tolerant Execution Wrapper
"""

from redis.asyncio import Redis
from redis.exceptions import ResponseError


class LuaScriptEngine:
    """Manages pre-loading Lua scripts into Redis SHA1 cache and executing via EVALSHA."""

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self._sha_map: dict[str, str] = {}

    async def register_script(self, name: str, script_body: str) -> str:
        """Loads script into Redis script cache and records SHA1 digest locally."""
        sha = await self.redis.script_load(script_body)
        self._sha_map[name] = sha
        return sha

    async def execute_reservation(
        self,
        stock_key: str,
        user_claims_key: str,
        quantity: int,
        user_id: str,
        script_body: str,
    ) -> int:
        """Executes inventory reservation atomically via EVALSHA with dynamic NOSCRIPT recovery."""
        sha = self._sha_map.get("reserve_stock")

        if not sha:
            sha = await self.register_script("reserve_stock", script_body)

        try:
            result = await self.redis.evalsha(
                sha,
                2,  # Number of KEYS passed
                stock_key,
                user_claims_key,  # KEYS[1], KEYS[2]
                quantity,
                user_id,  # ARGV[1], ARGV[2]
            )
            return int(result)

        except ResponseError as e:
            # Defensive Boundary Recovery: Catch Redis restart/script flush
            if "NOSCRIPT" in str(e):
                sha = await self.register_script("reserve_stock", script_body)
                result = await self.redis.evalsha(
                    sha,
                    2,
                    stock_key,
                    user_claims_key,
                    quantity,
                    user_id,
                )
                return int(result)

            raise e