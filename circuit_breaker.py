import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable, Optional, Tuple, Type
from fastapi import HTTPException, status

logger = logging.getLogger("circuit_breaker")


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenException(Exception):
    """Raised immediately when execution is blocked by an OPEN circuit."""

    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_state_change = time.monotonic()

        # Protects state updates & probe exclusivity in async runtime
        self._lock = asyncio.Lock()

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        async with self._lock:
            now = time.monotonic()

            # 1. Check if OPEN circuit recovery timeout has expired
            if self.state == CircuitState.OPEN:
                if now - self.last_state_change >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.last_state_change = now
                else:
                    # Circuit still locked OPEN — reject fast!
                    raise CircuitBreakerOpenException(
                        "Circuit is OPEN. Fast-failing downstream request."
                    )

            # 2. Handle HALF_OPEN exclusivity
            if self.state == CircuitState.HALF_OPEN:
                # The single caller proceeding past this block acts as our probe scout
                pass

        # Execute downstream call OUTSIDE the state lock so we don't stall parallel CLOSED calls
        try:
            result = await func(*args, **kwargs)
        except Exception as exc:
            await self._on_failure()
            raise exc
        else:
            await self._on_success()
            return result

    async def _on_success(self) -> None:
        async with self._lock:
            if self.state in (CircuitState.HALF_OPEN, CircuitState.CLOSED):
                self.failure_count = 0
                self.state = CircuitState.CLOSED

    async def _on_failure(self) -> None:
        async with self._lock:
            self.failure_count += 1
            if (
                self.state == CircuitState.HALF_OPEN
                or self.failure_count >= self.failure_threshold
            ):
                self.state = CircuitState.OPEN
                self.last_state_change = time.monotonic()


class TargetedCircuitBreaker(CircuitBreaker):
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        monitored_exceptions: Tuple[Type[Exception], ...] = (
            TimeoutError,
            ConnectionError,
            OSError,
        ),
    ):
        super().__init__(failure_threshold, recovery_timeout)
        self.monitored_exceptions = monitored_exceptions

    async def call_with_fallback(
        self,
        func: Callable,
        fallback: Optional[Callable] = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        try:
            return await self.call(func, *args, **kwargs)

        except CircuitBreakerOpenException:
            logger.warning("Circuit OPEN: Executing fallback or shedding load.")
            if fallback:
                return await fallback(*args, **kwargs)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service temporarily unavailable due to downstream degradation. Please retry later.",
                headers={"Retry-After": str(int(self.recovery_timeout))},
            )

        except Exception as exc:
            # ONLY increment failure count for true infrastructure/network faults
            if isinstance(exc, self.monitored_exceptions):
                logger.error(
                    f"Monitored infrastructure fault captured: {type(exc).__name__}"
                )
                await self._on_failure()
                if fallback:
                    return await fallback(*args, **kwargs)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Downstream storage interface connection failure.",
                )

            # Application/Validation errors bubble up cleanly without tripping the circuit
            raise exc