"""
WebhookEvent schema の表示用マスキングテスト
"""
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.webhook_event import WebhookEvent


def test_webhook_event_response_masks_payload_on_dump():
    """
    WebhookEventレスポンスはpayloadの生値をそのままdumpしない
    """
    response = WebhookEvent(
        id=uuid4(),
        event_id="evt_test_123",
        event_type="invoice.payment_succeeded",
        source="stripe",
        billing_id=None,
        office_id=None,
        payload={
            "id": "evt_test_123",
            "type": "invoice.payment_succeeded",
            "data": {
                "object": {
                    "id": "in_1234567890abcdef",
                    "customer": "cus_1234567890abcdef",
                    "customer_email": "payer@example.com",
                    "client_secret": "secret-value",
                },
            },
            "unexpected": "raw unexpected value",
        },
        status="success",
        error_message=None,
        processed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )

    dumped_payload = response.model_dump()["payload"]
    serialized_payload = str(dumped_payload)

    assert dumped_payload["id"] == "evt_test_123"
    assert dumped_payload["data"]["object"]["id"] == "<present>"
    assert dumped_payload["data"]["object"]["customer"] == "<present>"
    assert dumped_payload["data"]["object"]["customer_email"] == "p***@example.com"
    assert dumped_payload["data"]["object"]["client_secret"] == "<redacted>"
    assert dumped_payload["unexpected"] == "<redacted>"
    assert "payer@example.com" not in serialized_payload
    assert "secret-value" not in serialized_payload
    assert "raw unexpected value" not in serialized_payload
