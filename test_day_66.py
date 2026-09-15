import uuid
from datetime import datetime
from models import OutboxEvent, OutboxStatus

def test_outbox_event_schema_defaults():
    """
    Verifies that OutboxEvent instantiates correctly with required payloads,
    explicit status, and retry count.
    """
    test_payload = {"item_id": 101, "user_id": "usr_999", "quantity": 1}
    
    event = OutboxEvent(
        event_type="INVENTORY_RESERVED",
        payload=test_payload,
        status=OutboxStatus.PENDING,
        retry_count="0"
    )

    # Assertions for schema invariants
    assert event.event_type == "INVENTORY_RESERVED"
    assert event.payload == test_payload
    assert event.status == OutboxStatus.PENDING
    assert event.retry_count == "0"
    
    assert hasattr(event, "id")
    assert hasattr(event, "created_at")
    
    print("✅ Day 66 Outbox Schema & Default Invariants Verified Successfully!")

if __name__ == "__main__":
    test_outbox_event_schema_defaults()