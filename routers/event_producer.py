import logging
from typing import Dict, Any, Optional
from redis.asyncio import Redis
from redis.exceptions import RedisError
from schemas import EventEnvelopeSchema

logger = logging.getLogger(__name__)


class EventProducer:
    """
    Asynchronous Event Producer responsible for serializing and publishing 
    system state changes into Redis Streams logs.
    """
    def __init__(self, redis_client: Redis):
        self.redis = redis_client

    async def publish_event(
        self, 
        stream_name: str, 
        event_type: str, 
        payload: Dict[str, Any],
        max_len: int = 10000
    ) -> Optional[str]:
        """
        Publishes a schema-validated event envelope to a designated Redis Stream.
        Enforces MAXLEN stream trimming to prevent memory bloat.
        """
        try:
            # 1. Instantiate and validate contract envelope
            envelope = EventEnvelopeSchema(
                event_type=event_type,
                payload=payload
            )

            # 2. Serialize envelope fields for Redis Stream compatibility
            fields = envelope.to_redis_fields()

            # 3. Append to Stream log with approximate capping (MAXLEN ~)
            entry_id = await self.redis.xadd(
                name=stream_name,
                fields=fields,
                maxlen=max_len,
                approximate=True
            )

            logger.info(
                f"[EventProducer] Published '{event_type}' | ID: {entry_id} | Stream: {stream_name}"
            )
            return entry_id.decode("utf-8") if isinstance(entry_id, bytes) else entry_id

        except RedisError as exc:
            # Non-blocking boundary: Log failure without breaking the primary DB transaction
            logger.critical(
                f"[EventProducer Failure] Failed publishing event '{event_type}' to stream '{stream_name}': {str(exc)}",
                exc_info=True
            )
            return None