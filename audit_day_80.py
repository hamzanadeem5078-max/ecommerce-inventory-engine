import asyncio
import logging
import time
from database import SessionLocal
from redis_db import get_redis_client
from circuit_breaker import TargetedCircuitBreaker, CircuitBreakerOpenException
from metrics import get_stream_metrics, evaluate_system_health, dispatch_webhook_alert

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("audit_day_80")

async def run_audit():
    logger.info("--- [MILESTONE 16 AUDIT] Starting End-to-End System Verification ---")
    
    # 1. Initialize Clients & Sessions
    redis_client = get_redis_client()
    db = SessionLocal()
    
    # Low threshold (3 failures) & short timeout (2.0s) for rapid testing
    breaker = TargetedCircuitBreaker(failure_threshold=3, recovery_timeout=2.0)
    
    try:
        # Pre-audit cleanup: Flush test keys to guarantee zero state leakage
        keys_to_purge = await redis_client.keys("alert:cooldown:*")
        if keys_to_purge:
            await redis_client.delete(*keys_to_purge)
            logger.info(f"Purged {len(keys_to_purge)} stale Redis cooldown keys.")

        logger.info("Block 1 Initialized: Database session active, Redis pool connected, Circuit Breaker armed.")

        # --- BLOCK 2: CIRCUIT BREAKER SIMULATION ---
        logger.info("--- Testing Circuit Breaker Lifecycle ---")

        async def mock_failing_service():
            raise ConnectionError("Simulated infrastructure network partition")

        async def mock_success_service():
            return "Payload processed successfully"

        async def mock_fallback():
            return "Fallback handler executed: Load shed gracefully"

        # Stage 1: Drive failures past threshold (3 failures)
        for i in range(3):
            try:
                await breaker.call_with_fallback(mock_failing_service, fallback=mock_fallback)
            except Exception:
                pass
        logger.info(f"Circuit state after 3 failures: {breaker.state.value}")

        # Stage 2: Test OPEN state fast-fail and fallback trigger
        fallback_result = await breaker.call_with_fallback(mock_failing_service, fallback=mock_fallback)
        logger.info(f"OPEN State Test Result -> {fallback_result}")

        # Stage 3: Wait out the recovery timeout
        logger.info("Sleeping for 2.1 seconds to expire recovery timeout...")
        await asyncio.sleep(2.1)

        # Stage 4: Test HALF_OPEN probe and return to CLOSED on success
        recovery_result = await breaker.call_with_fallback(mock_success_service, fallback=mock_fallback)
        logger.info(f"Recovery Probe Result -> {recovery_result} | Final Circuit State: {breaker.state.value}")

        # --- BLOCK 3: TELEMETRY & WEBHOOK COOLDOWN TEST ---
        logger.info("--- Testing Metrics, Health Evaluation & Webhook Cooldown ---")
        
        mock_metrics = {
            "stream_key": "orders:stream",
            "group_name": "order_processing_group",
            "stream_length": 5000,
            "pending_count": 300,
            "consumer_count": 2,
            "lag": 2500,  # Exceeds LAG_CRITICAL_THRESHOLD (2000)
            "status": "healthy"
        }

        evaluated = evaluate_system_health(mock_metrics)
        logger.info(f"Health Classification Result: {evaluated['health_classification']}")
        logger.info(f"Generated Alerts: {evaluated['alerts']}")

        dummy_webhook_url = "https://httpbin.org/post"
        
        # First dispatch should succeed and lock the cooldown key in Redis
        logger.info("Triggering first webhook dispatch...")
        await dispatch_webhook_alert(redis_client, dummy_webhook_url, evaluated)
        
        # Second immediate dispatch should be suppressed by Redis cooldown
        logger.info("Triggering second dispatch immediately to verify cooldown suppression...")
        await dispatch_webhook_alert(redis_client, dummy_webhook_url, evaluated)

    finally:
        db.close()
        logger.info("--- [MILESTONE 16 AUDIT] Test Harness Teardown Complete ---")

if __name__ == "__main__":
    asyncio.run(run_audit())