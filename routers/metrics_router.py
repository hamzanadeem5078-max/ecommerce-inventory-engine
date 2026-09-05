from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from dependencies import get_redis_db
from metrics import get_stream_metrics, evaluate_system_health

router = APIRouter(prefix="/metrics", tags=["System Metrics & Observability"])

@router.get("/stream", status_code=status.HTTP_200_OK)
async def get_stream_health_telemetry(
    stream_key: str = "orders:stream",
    group_name: str = "order_processing_group",
    redis_client: Redis = Depends(get_redis_db)
):
    """
    Non-blocking endpoint probing stream length, consumer lag, and PEL backpressure.
    Returns classified system health state and active threshold alerts.
    """
    # 1. Fetch O(1)/O(G) Redis telemetry
    raw_metrics = await get_stream_metrics(
        redis_client=redis_client, 
        stream_key=stream_key, 
        group_name=group_name
    )
    
    # 2. Evaluate against health bounds
    evaluated_telemetry = evaluate_system_health(raw_metrics)
    
    # 3. If system is uninitialized, return 200 with notice (prevents orchestrator boot-loops)
    if raw_metrics.get("status") == "uninitialized":
        return {
            "status": "UNINITIALIZED",
            "message": "Stream or Consumer Group not yet created.",
            "telemetry": evaluated_telemetry
        }

    return evaluated_telemetry