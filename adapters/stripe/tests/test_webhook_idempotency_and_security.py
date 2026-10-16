"""
Tests for Stripe Webhook cryptographic security, replay protection, and duplicate deduplication.
Säule 2 (Idempotenz) und Säule 3 (Sicherheit) des Software Testing Audit Frameworks.
"""

import json
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from stripe_adapter.client import StripeClient
from stripe_adapter.db_models import StripeTransaction, StripeWebhookLog
from stripe_adapter.models import OrderStatus


@pytest.fixture
def existing_transaction(db_session: Session) -> StripeTransaction:
    tx = StripeTransaction(
        order_id="ORD-WEBHOOK-01",
        stripe_id="cs_test_wh_session_1",
        payment_type="checkout_session",
        status=OrderStatus.PENDING_PAYMENT.value,
        amount=50.00,
        amount_cents=5000,
        currency="USD",
        customer_email="wh_buyer@example.com",
        description="Webhook Test Order",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(tx)
    db_session.commit()
    db_session.refresh(tx)
    return tx


@pytest.fixture
def existing_intent_transaction(db_session: Session) -> StripeTransaction:
    tx = StripeTransaction(
        order_id="ORD-WEBHOOK-02",
        stripe_id="pi_test_wh_intent_2",
        payment_intent_id="pi_test_wh_intent_2",
        payment_type="payment_intent",
        status=OrderStatus.PENDING_PAYMENT.value,
        amount=85.00,
        amount_cents=8500,
        currency="USD",
        customer_email="wh_buyer2@example.com",
        description="Intent Webhook Test",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(tx)
    db_session.commit()
    db_session.refresh(tx)
    return tx


def test_webhook_checkout_session_completed(
    test_client: TestClient,
    db_session: Session,
    existing_transaction: StripeTransaction,
    test_settings,
):
    event_payload = {
        "id": "evt_cs_completed_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": existing_transaction.stripe_id,
                "client_reference_id": existing_transaction.order_id,
                "payment_status": "paid",
                "payment_intent": "pi_created_from_session_1",
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    current_time = int(time.time())
    sig = StripeClient.compute_webhook_signature(raw_body, test_settings.stripe_webhook_secret, current_time)
    header = f"t={current_time},v1={sig}"

    resp = test_client.post(
        "/api/v1/stripe/webhook",
        content=raw_body,
        headers={"Stripe-Signature": header, "Content-Type": "application/json"},
    )

    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "success"
    assert res_data["processed"] is True
    assert res_data["order_id"] == "ORD-WEBHOOK-01"

    # Verify DB transaction updated to PAID
    db_session.expire_all()
    tx = db_session.query(StripeTransaction).filter(StripeTransaction.order_id == "ORD-WEBHOOK-01").first()
    assert tx.status == OrderStatus.PAID.value
    assert tx.paid_at is not None
    assert tx.payment_intent_id == "pi_created_from_session_1"

    # Verify audit log
    log = db_session.query(StripeWebhookLog).filter(StripeWebhookLog.event_id == "evt_cs_completed_1").first()
    assert log is not None
    assert log.processed_status == "PROCESSED"
    assert log.is_valid_signature is True


def test_webhook_payment_intent_succeeded(
    test_client: TestClient,
    db_session: Session,
    existing_intent_transaction: StripeTransaction,
    test_settings,
):
    event_payload = {
        "id": "evt_pi_succeeded_2",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": existing_intent_transaction.stripe_id,
                "metadata": {"order_id": existing_intent_transaction.order_id},
                "status": "succeeded",
                "charges": {
                    "data": [
                        {
                            "receipt_url": "https://pay.stripe.com/receipts/test_receipt_123",
                            "payment_method_details": {"type": "card"},
                        }
                    ]
                },
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    current_time = int(time.time())
    sig = StripeClient.compute_webhook_signature(raw_body, test_settings.stripe_webhook_secret, current_time)
    header = f"t={current_time},v1={sig}"

    resp = test_client.post(
        "/api/v1/stripe/webhook",
        content=raw_body,
        headers={"Stripe-Signature": header, "Content-Type": "application/json"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    db_session.expire_all()
    tx = db_session.query(StripeTransaction).filter(StripeTransaction.order_id == "ORD-WEBHOOK-02").first()
    assert tx.status == OrderStatus.PAID.value
    assert tx.receipt_url == "https://pay.stripe.com/receipts/test_receipt_123"
    assert tx.payment_method == "card"


def test_webhook_payment_intent_failed(
    test_client: TestClient,
    db_session: Session,
    existing_intent_transaction: StripeTransaction,
    test_settings,
):
    event_payload = {
        "id": "evt_pi_failed_3",
        "type": "payment_intent.payment_failed",
        "data": {
            "object": {
                "id": existing_intent_transaction.stripe_id,
                "metadata": {"order_id": existing_intent_transaction.order_id},
                "last_payment_error": {"message": "Your card was declined."},
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    current_time = int(time.time())
    sig = StripeClient.compute_webhook_signature(raw_body, test_settings.stripe_webhook_secret, current_time)
    header = f"t={current_time},v1={sig}"

    resp = test_client.post(
        "/api/v1/stripe/webhook",
        content=raw_body,
        headers={"Stripe-Signature": header, "Content-Type": "application/json"},
    )

    assert resp.status_code == 200
    db_session.expire_all()
    tx = db_session.query(StripeTransaction).filter(StripeTransaction.order_id == "ORD-WEBHOOK-02").first()
    assert tx.status == OrderStatus.FAILED.value
    assert tx.failure_reason == "Your card was declined."


def test_webhook_idempotency_duplicate_event(
    test_client: TestClient,
    db_session: Session,
    existing_transaction: StripeTransaction,
    test_settings,
):
    event_payload = {
        "id": "evt_duplicate_test_4",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": existing_transaction.stripe_id,
                "payment_status": "paid",
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    current_time = int(time.time())
    sig = StripeClient.compute_webhook_signature(raw_body, test_settings.stripe_webhook_secret, current_time)
    header = f"t={current_time},v1={sig}"

    # First delivery: processed
    resp1 = test_client.post(
        "/api/v1/stripe/webhook",
        content=raw_body,
        headers={"Stripe-Signature": header, "Content-Type": "application/json"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "success"
    assert resp1.json()["processed"] is True

    # Second delivery with identical event_id: idempotent ignore
    resp2 = test_client.post(
        "/api/v1/stripe/webhook",
        content=raw_body,
        headers={"Stripe-Signature": header, "Content-Type": "application/json"},
    )
    assert resp2.status_code == 200
    res2 = resp2.json()
    assert res2["status"] == "already_processed"
    assert res2["processed"] is False
    assert "Duplicate" in res2["details"]

    # Verify both log rows exist: one PROCESSED, one DUPLICATE_IGNORED
    logs = db_session.query(StripeWebhookLog).filter(StripeWebhookLog.event_id == "evt_duplicate_test_4").all()
    assert len(logs) == 2
    statuses = [log_item.processed_status for log_item in logs]
    assert "PROCESSED" in statuses
    assert "DUPLICATE_IGNORED" in statuses


def test_webhook_signature_rejection(
    test_client: TestClient,
    db_session: Session,
    test_settings,
):
    raw_body = b'{"id": "evt_fraud", "type": "payment_intent.succeeded"}'
    current_time = int(time.time())
    fake_header = f"t={current_time},v1=badbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadb"

    resp = test_client.post(
        "/api/v1/stripe/webhook",
        content=raw_body,
        headers={"Stripe-Signature": fake_header, "Content-Type": "application/json"},
    )

    assert resp.status_code == 403
    assert "Forbidden" in resp.json()["detail"]

    # Audit log must record the failed attempt
    log = db_session.query(StripeWebhookLog).filter(StripeWebhookLog.event_id == "evt_fraud").first()
    assert log is not None
    assert log.processed_status == "SIGNATURE_FAILED"
    assert log.is_valid_signature is False
