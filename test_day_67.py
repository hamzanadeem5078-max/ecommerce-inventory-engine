# test_day_67.py
import asyncio
import pytest
from unittest.mock import AsyncMock
from circuit_breaker import CircuitState
from worker import process_outbox_batch, redis_circuit_breaker

@pytest.mark.asyncio
async def test_circuit_breaker_aborts_batch_dispatch():
    # 1. Force the circuit breaker into an OPEN state using the correct enum
    redis_circuit_breaker.state = CircuitState.OPEN
    
    # 2. Mock database and Redis clients
    db_mock = AsyncMock()
    redis_mock = AsyncMock()
    
    # 3. Execute batch processor under open circuit conditions
    processed_count = await process_outbox_batch(db_mock, redis_mock, batch_size=10)
    
    # 4. Assertions: Should return 0 instantly without touching DB or Redis network sockets
    assert processed_count == 0, "Batch dispatcher should have aborted execution!"
    db_mock.begin.assert_not_called()
    redis_mock.pipeline.assert_not_called()
    
    print("SUCCESS: Day 67 Circuit Breaker & Pipeline protection verified! Open state successfully halts dispatch.")

if __name__ == "__main__":
    asyncio.run(test_circuit_breaker_aborts_batch_dispatch())