import json
import logging
import redis.asyncio as aioredis
from opentelemetry import trace
from sqlalchemy.orm import Session

from circuit_breaker import TargetedCircuitBreaker, CircuitBreakerOpenException
import models

logger = logging.getLogger(__name__)

# Single circuit breaker instance guarding Redis Stream operations across the module
global_circuit_breaker = TargetedCircuitBreaker(
    failure_threshold=5,
    recovery_timeout=30.0,
    monitored_exceptions=(TimeoutError, ConnectionError, OSError, aioredis.RedisError)
)


def _get_w3c_traceparent() -> str | None:
    """Extracts active OTel span context and formats as W3C traceparent string."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        return f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-{ctx.trace_flags:02x}"
    return None


def _build_stream_payload(event_type: str, payload: dict) -> dict:
    """Constructs flat Redis XADD dictionary with optional W3C trace context injection."""
    data = {
        "event_type": event_type,
        "payload": json.dumps(payload)
    }
    tp = _get_w3c_traceparent()
    if tp:
        data["traceparent"] = tp
    return data


class EventProducer:
    """
    Legacy/Standard Event Producer for direct Redis Stream publishing.
    """
    def __init__(self, redis_client: aioredis.Redis):
        self.redis_client = redis_client

    async def publish_event(self, stream_name: str, event_type: str, payload: dict):
        """
        Publishes an event directly to a Redis Stream without fallback.
        """
        try:
            data = _build_stream_payload(event_type, payload)
            message_id = await self.redis_client.xadd(stream_name, data)
            logger.info(f"Published event '{event_type}' to stream '{stream_name}' with ID: {message_id}")
            return message_id
        except Exception as e:
            logger.error(f"Failed to publish event '{event_type}' to '{stream_name}': {str(e)}")
            raise e


class ResilientEventProducer:
    """
    Day 69: High-concurrency Resilient Event Producer.
    Executes stream operations within a TargetedCircuitBreaker. 
    Falls back directly to PostgreSQL OutboxEvent when the circuit is OPEN or Redis is unreachable.
    """
    def __init__(self, redis_client: aioredis.Redis):
        self.redis_client = redis_client
        self.breaker = global_circuit_breaker

    async def _raw_redis_publish(self, stream_name: str, event_type: str, payload: dict):
        data = _build_stream_payload(event_type, payload)
        return await self.redis_client.xadd(stream_name, data)

    def _persist_to_outbox(self, db: Session, event_type: str, payload: dict, last_error: str) -> None:
        """
        Fallback path: Persists the event directly into the outbox_events table.
        Uses the active DB transaction session so it commits atomically alongside business logic.
        """
        outbox_entry = models.OutboxEvent(
            event_type=event_type,
            payload=payload,
            status=models.OutboxStatus.PENDING,
            last_error=last_error
        )
        db.add(outbox_entry)
        logger.warning(
            f"[Circuit Breaker Fallback] Diverted event '{event_type}' to Postgres Outbox table. "
            f"Reason: {last_error}"
        )

    async def publish_with_fallback(
        self, 
        db: Session, 
        stream_name: str, 
        event_type: str, 
        payload: dict
    ) -> bool:
        """
        Attempts publishing to Redis Stream wrapped in the Circuit Breaker.
        
        Returns:
            bool: True if published directly to Redis Stream (Healthy State).
                  False if diverted to Postgres Outbox (Degraded State).
        """
        try:
            await self.breaker.call(
                self._raw_redis_publish,
                stream_name=stream_name,
                event_type=event_type,
                payload=payload
            )
            return True

        except (CircuitBreakerOpenException, aioredis.RedisError, TimeoutError, ConnectionError, OSError) as exc:
            err_msg = f"{type(exc).__name__}: {str(exc)}"
            self._persist_to_outbox(db=db, event_type=event_type, payload=payload, last_error=err_msg)
            return False