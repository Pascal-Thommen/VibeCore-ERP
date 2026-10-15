"""
Tests for ACID database guarantees, idempotency defense, and resilience.
Säule 2 (Datenintegrität und Transaktionen) des Software Testing Audit Frameworks.
"""

from unittest.mock import MagicMock
import httpx
import pytest
from sqlalchemy.orm import Session

from stripe_adapter.client import StripeError
from stripe_adapter.db_models import StripeTransaction
from stripe_adapter.models import (
    CreateCheckoutSessionRequest,
    CreatePaymentIntentRequest,
    OrderStatus,
)
from stripe_adapter.service import StripePaymentService


@pytest.mark.asyncio
async def test_checkout_session_idempotency_key(monkeypatch, db_session: Session, test_settings):
    stripe_call_count = 0

    async def mock_post(client_self, url, **kwargs):
        nonlocal stripe_call_count
        stripe_call_count += 1
        return httpx.Response(
            status_code=200,
            json={
                "id": "cs_test_idemp_1",
                "url": "https://checkout.stripe.com/c/pay/cs_test_idemp_1",
                "payment_status": "unpaid",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    service = StripePaymentService(custom_settings=test_settings)
    req = CreateCheckoutSessionRequest(
        order_id="ORD-IDEMP-01",
        amount_total=40.00,
        currency="USD",
        description="Idempotent Test",
        customer_email="idem@example.com",
    )

    # First call: registers with Stripe
    resp1 = await service.create_checkout_session(
        db=db_session,
        request=req,
        idempotency_key="KEY-UNIQUE-123",
    )
    assert resp1.stripe_id == "cs_test_idemp_1"
    assert stripe_call_count == 1

    # Second call with same idempotency key: must NOT call Stripe API again
    resp2 = await service.create_checkout_session(
        db=db_session,
        request=req,
        idempotency_key="KEY-UNIQUE-123",
    )
    assert resp2.stripe_id == "cs_test_idemp_1"
    assert resp2.order_id == "ORD-IDEMP-01"
    assert stripe_call_count == 1  # Verify no duplicate network call

    # DB verify single row
    rows = db_session.query(StripeTransaction).filter(StripeTransaction.order_id == "ORD-IDEMP-01").all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_payment_intent_repeat_order_id(monkeypatch, db_session: Session, test_settings):
    stripe_call_count = 0

    async def mock_post(client_self, url, **kwargs):
        nonlocal stripe_call_count
        stripe_call_count += 1
        return httpx.Response(
            status_code=200,
            json={
                "id": "pi_test_repeat_01",
                "client_secret": "pi_secret_01",
                "status": "requires_payment_method",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    service = StripePaymentService(custom_settings=test_settings)
    req = CreatePaymentIntentRequest(
        order_id="ORD-REPEAT-02",
        amount=75.00,
        currency="USD",
        description="Repeat Order ID Test",
    )

    resp1 = await service.create_payment_intent(db=db_session, request=req)
    assert resp1.stripe_id == "pi_test_repeat_01"
    assert stripe_call_count == 1

    # Repeat with same order_id (e.g. caller retry without idempotency key)
    resp2 = await service.create_payment_intent(db=db_session, request=req)
    assert resp2.stripe_id == "pi_test_repeat_01"
    assert stripe_call_count == 1  # No duplicate charge created

    rows = db_session.query(StripeTransaction).filter(StripeTransaction.order_id == "ORD-REPEAT-02").all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_atomic_rollback_on_database_failure(monkeypatch, db_session: Session, test_settings):
    async def mock_post(client_self, url, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "id": "cs_test_rollback",
                "url": "https://checkout.stripe.com/c/pay/cs_test_rollback",
                "payment_status": "unpaid",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    # Force commit failure
    mock_db = MagicMock(wraps=db_session)
    mock_db.commit.side_effect = RuntimeError("Disk full / DB connection lost")

    service = StripePaymentService(custom_settings=test_settings)
    req = CreateCheckoutSessionRequest(
        order_id="ORD-FAIL-ROLLBACK",
        amount_total=20.00,
        currency="USD",
        description="Rollback Test",
        customer_email="fail@example.com",
    )

    with pytest.raises(StripeError) as exc_info:
        await service.create_checkout_session(db=mock_db, request=req)

    assert "Database error persisting transaction" in str(exc_info.value)
    mock_db.rollback.assert_called_once()
