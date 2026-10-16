"""Tests for outbound signed WebhookDispatcher and Dead-Letter Queue."""

from unittest.mock import MagicMock, patch
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bancard.database import Base, DeadLetterWebhook
from bancard.metrics import metrics
from bancard.webhook_dispatcher import WebhookDispatcher


@pytest.fixture
def db():
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def test_webhook_successful_dispatch(db):
    dispatcher = WebhookDispatcher(secret="test_secret", timeout=2.0, max_retries=2, backoff_factor=0.01)

    mock_response = MagicMock(status_code=200, text="OK")

    with patch("httpx.Client.post", return_value=mock_response) as mock_post:
        results = dispatcher.dispatch_event(
            db=db,
            event_type="payment.bancard.approved",
            data={"shop_process_id": 10001, "amount": "45000.00"},
            target_urls=["http://test-consumer.local/webhook"],
        )

        assert len(results) == 1
        assert results[0]["status"] == "delivered"
        assert results[0]["attempts"] == 1
        assert mock_post.call_count == 1

        # Check signature header was included
        _, kwargs = mock_post.call_args
        headers = kwargs.get("headers", {})
        assert "X-VibeCore-Signature" in headers
        assert "X-VibeCore-Timestamp" in headers


def test_webhook_retries_and_dead_letter_fallback(db):
    dispatcher = WebhookDispatcher(secret="test_secret", timeout=1.0, max_retries=3, backoff_factor=0.001)

    # Simulate network exception on all attempts
    with patch("httpx.Client.post", side_effect=httpx.ConnectError("Connection refused")) as mock_post:
        results = dispatcher.dispatch_event(
            db=db,
            event_type="payment.bancard.rejected",
            data={"shop_process_id": 10002, "reason": "declined"},
            target_urls=["http://unreachable-endpoint.local/webhook"],
        )

        assert len(results) == 1
        assert results[0]["status"] == "dead_letter"
        assert mock_post.call_count == 3

        # Must be persisted in DeadLetterWebhook table
        dead_letters = db.query(DeadLetterWebhook).all()
        assert len(dead_letters) == 1
        dl = dead_letters[0]
        assert dl.target_url == "http://unreachable-endpoint.local/webhook"
        assert dl.event_type == "payment.bancard.rejected"
        assert dl.attempts == 3
        assert dl.status == "FAILED"
        assert "ConnectError" in dl.error_message


def test_retry_dead_letter_success(db):
    dispatcher = WebhookDispatcher(secret="test_secret", timeout=2.0)

    # Create failed dead letter in DB
    dl = DeadLetterWebhook(
        target_url="http://recovered-service.local/webhook",
        event_type="payment.bancard.approved",
        payload='{"event_id":"evt_1","data":{}}',
        signature="t=123,v1=abc",
        attempts=3,
        status="FAILED",
    )
    db.add(dl)
    db.commit()

    mock_resp = MagicMock(status_code=200, text="OK")
    with patch("httpx.Client.post", return_value=mock_resp):
        success = dispatcher.retry_dead_letter(db=db, dead_letter_id=dl.id)
        assert success is True

        db.refresh(dl)
        assert dl.status == "REPROCESSED"
        assert dl.attempts == 4
