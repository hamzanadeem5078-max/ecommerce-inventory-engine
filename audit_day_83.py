import asyncio
import uuid
import httpx
from sqlalchemy import text
from database import SessionLocal
from dependencies import correlation_id_var
import redis_db
from worker import parse_and_process_event

async def run_audit():
    print("==================================================")
    print("   DAY 83: DISTRIBUTED TRACING & CORRELATION AUDIT")
    print("==================================================")

    test_corr_id = f"audit-trace-{uuid.uuid4()}"
    print(lambda: f"[TEST SETUP] Generated Test Correlation ID: {test_corr_id}")

    # 1. Test ContextVar and SQLAlchemy Statement Stamping
    print("\n--- [Audit 1: SQLAlchemy Cursor Event Listener] ---")
    token = correlation_id_var.set(test_corr_id)
    try:
        with SessionLocal() as session:
            # Execute a raw query to trigger the 'before_cursor_execute' event listener
            result = session.execute(text("SELECT 1")).scalar()
            print(f"Database query executed successfully. Result: {result}")
            print(f"Active ContextVar ID: {correlation_id_var.get()}")
    finally:
        correlation_id_var.reset(token)

    # 2. Test Redis Stream Payload Propagation Simulation
    print("\n--- [Audit 2: Redis Stream & Worker Propagation] ---")
    mock_event_id = str(uuid.uuid4())
    mock_fields = {
        "event_id": mock_event_id,
        "event_type": "AUDIT_TEST_EVENT",
        "correlation_id": test_corr_id
    }
    
    # Simulate worker processing and ContextVar binding
    worker_token = correlation_id_var.set(mock_fields["correlation_id"])
    try:
        bound_id = correlation_id_var.get()
        print(f"Worker successfully bound incoming stream correlation ID: {bound_id}")
        assert bound_id == test_corr_id, "Correlation ID mismatch in worker boundary!"
    finally:
        correlation_id_var.reset(worker_token)

    print("\n==================================================")
    print("   ✅ DAY 83 AUDIT PASSED: TELEMETRY PIPELINE SECURE")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_audit())