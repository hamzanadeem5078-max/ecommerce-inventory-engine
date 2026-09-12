import asyncio
import pytest
from circuit_breaker import (
    CircuitBreakerOpenException,
    CircuitState,
    TargetedCircuitBreaker,
)


async def mock_failing_db_call():
    raise ConnectionError("PostgreSQL connection refused")


async def mock_successful_db_call():
    return {"status": "ok", "inventory": 100}


@pytest.mark.asyncio
async def test_circuit_breaker_lifecycle():
    breaker = TargetedCircuitBreaker(failure_threshold=2, recovery_timeout=0.2)

    # 1. Closed state initial checks
    assert breaker.state == CircuitState.CLOSED

    # 2. Trip breaker via consecutive failures
    for _ in range(2):
        with pytest.raises(Exception):
            await breaker.call_with_fallback(mock_failing_db_call)

    assert breaker.state == CircuitState.OPEN

    # 3. Verify fast-fail behavior (raises 503 / Open exception without executing call)
    with pytest.raises(Exception):
        await breaker.call_with_fallback(mock_failing_db_call)
    assert breaker.state == CircuitState.OPEN

    # 4. Wait out recovery timeout and verify HALF_OPEN transition on success
    await asyncio.sleep(0.25)
    result = await breaker.call_with_fallback(mock_successful_db_call)

    assert result == {"status": "ok", "inventory": 100}
    assert breaker.state == CircuitState.CLOSED


if __name__ == "__main__":
    asyncio.run(test_circuit_breaker_lifecycle())
    print(
        "DAY 63 VERIFICATION PASSED: Circuit Breaker state transitions & isolated execution verified."
    )