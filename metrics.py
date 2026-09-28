import logging
import httpx
from typing import Dict, Any
from datetime import datetime, timezone
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from prometheus_client import Gauge, Counter, generate_latest, CONTENT_TYPE_LATEST

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
        metrics["stream_length"] = await redis_client.xlen(stream_key)
        groups = await redis_client.xinfo_groups(stream_key)
        
        target_group = next((g for g in groups if g.get("name") == group_name or g.get("name") == group_name.encode()), None)

        if target_group:
            metrics["pending_count"] = target_group.get("pending", target_group.get(b"pending", 0))
            metrics["consumer_count"] = target_group.get("consumers", target_group.get(b"consumers", 0))
            metrics["lag"] = target_group.get("lag", target_group.get(b"lag", 0))
            
            if metrics["lag"] is None:
                metrics["lag"] = 0
        else:
            metrics["status"] = "group_not_found"

    except ResponseError as e:
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
ALERT_COOLDOWN_SECONDS = 300  # 5-minute suppression window per alert type

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

    if consumers == 0 and status == "healthy" and lag > 0:
        health_status = "CRITICAL"
        alerts.append("NO_ACTIVE_CONSUMERS: Worker process down while stream has unread messages.")

    if lag >= LAG_CRITICAL_THRESHOLD:
        health_status = "CRITICAL"
        alerts.append(f"CRITICAL_STREAM_LAG: Lag ({lag}) exceeded threshold ({LAG_CRITICAL_THRESHOLD}).")
    elif lag >= LAG_WARNING_THRESHOLD and health_status != "CRITICAL":
        health_status = "WARNING"
        alerts.append(f"HIGH_STREAM_LAG: Lag ({lag}) approaching threshold ({LAG_WARNING_THRESHOLD}).")

    if pending >= PENDING_WARNING_THRESHOLD and health_status != "CRITICAL":
        health_status = "WARNING"
        alerts.append(f"HIGH_PENDING_ENTRIES: Unacked messages ({pending}) indicate worker slowdown or processing bottlenecks.")

    metrics["health_classification"] = health_status
    metrics["alerts"] = alerts
    return metrics


async def dispatch_webhook_alert(redis_client: Redis, webhook_url: str, metrics: Dict[str, Any]) -> None:
    """
    Dispatches asynchronous webhook alerts for non-healthy classifications,
    guaranteeing non-blocking execution and Redis-backed cooldown suppression.
    """
    health_status = metrics.get("health_classification", "HEALTHY")
    if health_status == "HEALTHY" or not webhook_url:
        return

    for alert in metrics.get("alerts", []):
        alert_key = f"alert:cooldown:{alert.split(':')[0]}"
        
        # Redis atomic set with NX and EX to prevent alert storms (thundering herd)
        acquired = await redis_client.set(alert_key, "1", ex=ALERT_COOLDOWN_SECONDS, nx=True)
        if not acquired:
            logger.debug(f"[ALERT SUPPRESSED] Cooldown active for alert: {alert}")
            continue

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "health_classification": health_status,
            "alert_message": alert,
            "metrics_snapshot": {
                "stream_key": metrics.get("stream_key"),
                "lag": metrics.get("lag"),
                "pending_count": metrics.get("pending_count"),
                "consumer_count": metrics.get("consumer_count")
            }
        }

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.post(webhook_url, json=payload)
                if response.status_code >= 400:
                    logger.warning(f"[WEBHOOK FAILED] Endpoint returned status {response.status_code}")
                else:
                    logger.info(f"[WEBHOOK DISPATCHED] Alert sent successfully for: {alert}")
        except httpx.RequestError as e:
            logger.error(f"[WEBHOOK ERROR] Network failure dispatching alert: {str(e)}")
        except Exception as e:
            logger.error(f"[WEBHOOK UNHANDLED] Unexpected error during webhook dispatch: {str(e)}")


# Bounded cardinality time-series definitions
dlq_depth_gauge = Gauge(
    "dlq_depth_total",
    "Number of items currently parked in Dead Letter Queues",
    ["queue_name"]
)

replay_counter = Counter(
    "dlq_replay_total",
    "Cumulative count of DLQ messages re-enqueued to active processing",
    ["queue_name", "status"]
)

outbox_lag_seconds_gauge = Gauge(
    "outbox_lag_seconds",
    "Delta in seconds between outbox event creation and consumer pickup",
    ["channel"]
)