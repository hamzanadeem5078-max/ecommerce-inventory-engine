import logging
from typing import Dict, Any
from redis.asyncio import Redis
from redis.exceptions import ResponseError

logger = logging.getLogger("metrics")

async def get_stream_metrics(
    redis_client: Redis, 
    stream_key: str = "orders:stream", 
    group_name: str = "order_processing_group"
) -> Dict[str, Any]:
    """
    Extracts stream length, pending message count, active consumer count, 
    and consumer group lag without blocking the Redis single thread.
    """
    metrics = {
        "stream_key": stream_key,
        "group_name": group_name,
        "stream_length": 0,
        "pending_count": 0,
        "consumer_count": 0,
        "lag": 0,
        "status": "healthy"
    }

    try:
        # O(1) Stream length query
        metrics["stream_length"] = await redis_client.xlen(stream_key)

        # O(N) where N is number of consumer groups (typically 1-5 groups)
        groups = await redis_client.xinfo_groups(stream_key)
        
        target_group = next((g for g in groups if g.get("name") == group_name or g.get("name") == group_name.encode()), None)

        if target_group:
            # redis-py returns dict keys as bytes or str depending on decode_responses flag
            metrics["pending_count"] = target_group.get("pending", target_group.get(b"pending", 0))
            metrics["consumer_count"] = target_group.get("consumers", target_group.get(b"consumers", 0))
            
            # Lag is directly available in Redis 7.0+
            metrics["lag"] = target_group.get("lag", target_group.get(b"lag", 0))
            
            # Fallback if lag is None (e.g. legacy Redis or uncomputed state)
            if metrics["lag"] is None:
                metrics["lag"] = 0
        else:
            metrics["status"] = "group_not_found"

    except ResponseError as e:
        # Handles 'ERR no such key' or 'NOGROUP No such key or consumer group' on cold start
        logger.warning(f"Metrics collection fallback for {stream_key}: {str(e)}")
        metrics["status"] = "uninitialized"
    except Exception as e:
        logger.error(f"Unexpected error inspecting stream metrics: {str(e)}")
        metrics["status"] = "error"

    return metrics



# Operational Thresholds
LAG_WARNING_THRESHOLD = 500
LAG_CRITICAL_THRESHOLD = 2000
PENDING_WARNING_THRESHOLD = 200

def evaluate_system_health(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates telemetry against failure bounds to classify system state into
    HEALTHY, WARNING, or CRITICAL. Distinguishes load spikes from dead workers.
    """
    health_status = "HEALTHY"
    alerts = []

    lag = metrics.get("lag", 0)
    pending = metrics.get("pending_count", 0)
    consumers = metrics.get("consumer_count", 0)
    status = metrics.get("status", "healthy")

    # Check worker vitality
    if consumers == 0 and status == "healthy" and lag > 0:
        health_status = "CRITICAL"
        alerts.append("NO_ACTIVE_CONSUMERS: Worker process down while stream has unread messages.")

    # Check stream backpressure (Lag)
    if lag >= LAG_CRITICAL_THRESHOLD:
        health_status = "CRITICAL"
        alerts.append(f"CRITICAL_STREAM_LAG: Lag ({lag}) exceeded threshold ({LAG_CRITICAL_THRESHOLD}).")
    elif lag >= LAG_WARNING_THRESHOLD and health_status != "CRITICAL":
        health_status = "WARNING"
        alerts.append(f"HIGH_STREAM_LAG: Lag ({lag}) approaching threshold ({LAG_WARNING_THRESHOLD}).")

    # Check unacknowledged message backlog (PEL leak / stuck workers)
    if pending >= PENDING_WARNING_THRESHOLD and health_status != "CRITICAL":
        health_status = "WARNING"
        alerts.append(f"HIGH_PENDING_ENTRIES: Unacked messages ({pending}) indicate worker slowdown or processing bottlenecks.")

    metrics["health_classification"] = health_status
    metrics["alerts"] = alerts
    return metrics