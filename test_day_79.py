import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, patch
from redis.asyncio import Redis
from metrics import get_stream_metrics, evaluate_system_health, dispatch_webhook_alert, ALERT_COOLDOWN_SECONDS

@pytest_asyncio.fixture
async def redis_client():
    client = Redis(host="localhost", port=6379, db=1)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()

@pytest.fixture
def mock_webhook():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        yield mock_post

@pytest.mark.asyncio
async def test_health_alert_and_webhook_cooldown(redis_client, mock_webhook):
    stream_key = "test:orders:stream"
    group_name = "test_group"
    webhook_url = "https://internal-alert-receiver.local/webhook"

    # 1. Setup consumer group and inject unread messages to simulate severe consumer lag
    await redis_client.xgroup_create(name=stream_key, groupname=group_name, id="0", mkstream=True)
    
    # Add messages to push lag above the critical threshold (2000)
    for i in range(2500):
        await redis_client.xadd(stream_key, {"order_id": f"ord_{i}", "event_type": "ORDER_CREATED"})

    # 2. Extract metrics (simulating monitor polling)
    metrics = await get_stream_metrics(redis_client, stream_key=stream_key, group_name=group_name)
    assert metrics["lag"] >= 2000

    # 3. Evaluate system health (Triggers 2 alerts: NO_ACTIVE_CONSUMERS and CRITICAL_STREAM_LAG)
    evaluated_metrics = evaluate_system_health(metrics)
    assert evaluated_metrics["health_classification"] == "CRITICAL"
    assert len(evaluated_metrics["alerts"]) == 2

    # 4. First Webhook Dispatch (Should trigger 2 posts for the 2 distinct alerts and acquire Redis cooldown keys)
    await dispatch_webhook_alert(redis_client, webhook_url, evaluated_metrics)
    assert mock_webhook.call_count == 2

    # Verify cooldown keys were set in Redis for both alerts
    for alert in evaluated_metrics["alerts"]:
        alert_type = alert.split(":")[0]
        cooldown_key = f"alert:cooldown:{alert_type}"
        ttl = await redis_client.ttl(cooldown_key)
        assert ttl > 0
        assert ttl <= ALERT_COOLDOWN_SECONDS

    # 5. Immediate Second Webhook Dispatch (Both should be suppressed by Redis cooldown)
    await dispatch_webhook_alert(redis_client, webhook_url, evaluated_metrics)
    
    # Assert call count did NOT increase (duplicates suppressed)
    assert mock_webhook.call_count == 2