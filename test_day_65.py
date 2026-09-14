import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from redis.exceptions import ResponseError
from dependencies import enforce_dynamic_rate_limit


@pytest.mark.anyio
async def test_enforce_dynamic_rate_limit_oom_handling():
    mock_request = MagicMock()
    mock_request.state.user_id = "test_user_oom"
    mock_request.state.user_tier = "standard"

    with patch("dependencies.get_redis_client") as mock_get_client, \
         patch("dependencies.LuaScriptEngine") as mock_lua_engine_cls:

        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_engine_instance = AsyncMock()
        # Simulate Redis throwing an OOM error during script execution
        mock_engine_instance.check_rate_limit.side_effect = ResponseError(
            "OOM command not allowed when used memory > 'maxmemory'"
        )
        mock_lua_engine_cls.return_value = mock_engine_instance

        with pytest.raises(HTTPException) as exc_info:
            await enforce_dynamic_rate_limit(mock_request)

        assert exc_info.value.status_code == 503
        assert "Memory boundary exceeded" in str(exc_info.value.detail)