import asyncio
from unittest.mock import AsyncMock
from metrics import get_stream_metrics, evaluate_system_health

def test_stream_metrics_and_health_evaluation():
    async def run_test():
        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.xlen.return_value = 5050
        mock_redis.xinfo_groups.return_value = [{
            "name": "inventory_workers",
            "pending": 250,
            "consumers": 2,
            "lag": 2100  # Exceeds critical threshold
        }]

        # 1. Test metric extraction
        metrics = await get_stream_metrics(
            mock_redis, 
            stream_key="orders:stream", 
            group_name="inventory_workers"
        )
        
        assert metrics["stream_length"] == 5050
        assert metrics["lag"] == 2100
        assert metrics["pending_count"] == 250
        assert metrics["consumer_count"] == 2

        # 2. Test health evaluation (Should trigger CRITICAL due to lag >= 2000)
        health = evaluate_system_health(metrics)
        
        assert health["health_classification"] == "CRITICAL"
        assert any("CRITICAL_STREAM_LAG" in alert for alert in health["alerts"])
        
        print("\n[PASS] Day 77 telemetry health classification verified successfully under load stress simulation.")

    asyncio.run(run_test())

if __name__ == "__main__":
    test_stream_metrics_and_health_evaluation()