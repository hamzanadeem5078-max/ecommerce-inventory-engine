# audit_day_70.py — End-to-End Resiliency & Circuit Breaker Audit Suite
import asyncio
import logging
from unittest.mock import AsyncMock
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
import models
from redis_db import get_redis_client
from event_producer import ResilientEventProducer, global_circuit_breaker
from circuit_breaker import CircuitState

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("audit_day_70")

async def clean_redis(r):
    try:
        await r.flushdb()
        logger.info("⚡ Redis keyspace flushed.")
    except Exception as e:
        logger.warning(f"⚠️ Redis offline ({type(e).__name__}); skipping flush and proceeding with fallback test.")

def clean_database(db: Session):
    db.query(models.OutboxEvent).delete()
    db.commit()
    logger.info("🗄️ PostgreSQL outbox table truncated/cleared.")

async def run_audit():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    r = get_redis_client()
    
    try:
        # --- BLOCK 1: CLEAN STATE HARNESS ---
        clean_database(db)
        await clean_redis(r)
        global_circuit_breaker.state = CircuitState.CLOSED
        global_circuit_breaker.failure_count = 0
        logger.info("[Block 1 PASS] Harness initialized to clean CLOSED state.")

        # --- BLOCK 2: FAULT INJECTION & OUTBOX FALLBACK ---
        producer = ResilientEventProducer(redis_client=r)
        # Mock _raw_redis_publish to raise ConnectionError, simulating Redis partition
        producer._raw_redis_publish = AsyncMock(side_effect=ConnectionError("Simulated Redis Network Partition"))

        test_payload = {"order_id": 9999, "sku": "FLASH-SKU-01", "qty": 1}
        success = await producer.publish_with_fallback(
            db=db,
            stream_name="test_stream",
            event_type="ORDER_CREATED",
            payload=test_payload
        )
        db.commit()  # Commit outbox persistence transaction
        assert success is False, "Expected publish_with_fallback to return False on degradation."
        
        # ORM assertion: verify zero data loss by inspecting outbox persistence contract
        db.expire_all()
        outbox_rows = db.query(models.OutboxEvent).all()
        assert len(outbox_rows) == 1, f"Expected 1 outbox fallback record, found {len(outbox_rows)}"
        row = outbox_rows[0]
        assert row.event_type == "ORDER_CREATED"
        assert row.payload == test_payload
        assert row.status == models.OutboxStatus.PENDING
        assert "ConnectionError" in (row.last_error or "")
        logger.info("[Block 2 PASS] Fault injection intercepted; 100% payload preserved in DB Outbox contract.")

        # --- BLOCK 3: STATE MACHINE TRANSITION & FAILURE THRESHOLD TRIP ---
        # Trip threshold is 5 failures. We already triggered 1 above. Let's trigger 4 more.
        for i in range(4):
            await producer.publish_with_fallback(
                db=db, stream_name="test_stream", event_type="ORDER_CREATED", payload=test_payload
            )
            db.commit()
        
        db.expire_all()
        assert global_circuit_breaker.state == CircuitState.OPEN, f'Expected OPEN state, got {global_circuit_breaker.state}'
        logger.info("[Block 3a PASS] Circuit breaker transitioned to OPEN after threshold reached.")

        # Verify fast-fail/outbox fallback continues safely while OPEN
        db.query(models.OutboxEvent).delete()
        db.commit()
        await producer.publish_with_fallback(
            db=db, stream_name="test_stream", event_type="ORDER_CREATED", payload=test_payload
        )
        db.commit()
        outbox_rows_open = db.query(models.OutboxEvent).all()
        assert len(outbox_rows_open) == 1, "OPEN circuit fallback outbox record missing."

        # Simulate recovery timeout expiration for HALF-OPEN transition probe test
        global_circuit_breaker.recovery_timeout = 0.05
        await asyncio.sleep(0.06)
        
        # Restore mock to healthy behavior for probe
        producer._raw_redis_publish = AsyncMock(return_value="1700000000000-0")
        
        # Next call should transition through HALF-OPEN to CLOSED upon success
        probe_success = await producer.publish_with_fallback(
            db=db, stream_name="test_stream", event_type="ORDER_RECOVERED", payload={"probe": True}
        )
        db.commit()
        assert probe_success is True, "Expected probe in HALF-OPEN to succeed against restored Redis."
        assert global_circuit_breaker.state == CircuitState.CLOSED, f'Expected CLOSED state post-recovery, got {global_circuit_breaker.state}'
        logger.info("[Block 3b PASS] HALF-OPEN probe succeeded; circuit healed back to CLOSED.")

        # --- BLOCK 4: ASSERTION SUMMARY ---
        logger.info("🎉 ALL DAY 70 RESILIENCY & CIRCUIT BREAKER AUDIT ASSERTIONS PASSED WITH ZERO DRIFT.")

    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run_audit())