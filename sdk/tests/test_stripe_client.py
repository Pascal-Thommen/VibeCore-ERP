"""Unit and contract tests for StripeClient (Stripe International Payments)."""

import json

import httpx
import pytest

from vibecore.exceptions import (
    AuthenticationError,
    PaymentGatewayError,
    PaymentNotFoundError,
    PaymentTimeoutError,
)
from vibecore.payments.stripe.client import StripeClient
from vibecore.payments.stripe.models import (
    CreateCheckoutSessionRequest,
    CreatePaymentIntentRequest,
    LineItemModel,
    OrderStatus,
    PaymentResponse,
    SyncPaymentResponse,
)


def test_stripe_client_health():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "healthy", "service": "stripe-adapter"})

    with StripeClient("http://stripe.test", transport=httpx.MockTransport(handler)) as client:
        resp = client.health()
        assert resp["status"] == "healthy"


def test_stripe_client_ready():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ready"
        return httpx.Response(200, json={"status": "ready", "database": True})

    with StripeClient("http://stripe.test", transport=httpx.MockTransport(handler)) as client:
        resp = client.ready()
        assert resp["status"] == "ready"


def test_stripe_client_create_checkout_session():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/stripe/checkout-sessions"
        assert request.headers.get("x-adapter-key") == "secret-stripe-key"
        assert request.headers.get("x-idempotency-key") == "idem-session-1"
        assert request.headers.get("x-correlation-id") == "corr-trace-1"
        body = json.loads(request.content.decode("utf-8"))
        assert body["order_id"] == "ORD-STRIPE-001"
        assert body["amount_total"] == 49.99
        assert body["currency"] == "USD"
        return httpx.Response(
            201,
            json={
                "order_id": "ORD-STRIPE-001",
                "stripe_id": "cs_test_abc123",
                "payment_type": "checkout_session",
                "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_abc123",
                "status": "INITIATED",
                "amount": 49.99,
                "amount_cents": 4999,
                "currency": "USD",
                "customer_email": "pascal@vibecore.io",
                "created_at": "2026-10-15T22:00:00Z",
            },
        )

    client = StripeClient(
        "http://stripe.test",
        api_key="secret-stripe-key",
        transport=httpx.MockTransport(handler),
    )
    req = CreateCheckoutSessionRequest(
        order_id="ORD-STRIPE-001",
        amount_total=49.99,
        currency="USD",
        description="VibeCore ERP International License",
        customer_email="pascal@vibecore.io",
        items=[
            LineItemModel(
                name="License Key",
                amount=49.99,
                quantity=1,
            )
        ],
    )
    session = client.create_checkout_session(
        req,
        idempotency_key="idem-session-1",
        correlation_id="corr-trace-1",
    )
    assert isinstance(session, PaymentResponse)
    assert session.stripe_id == "cs_test_abc123"
    assert session.amount_cents == 4999
    assert session.status == OrderStatus.INITIATED
    assert session.checkout_url == "https://checkout.stripe.com/c/pay/cs_test_abc123"
    client.close()


def test_stripe_client_create_payment_intent():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/stripe/payment-intents"
        body = json.loads(request.content.decode("utf-8"))
        assert body["amount"] == 100.0
        assert body["currency"] == "EUR"
        return httpx.Response(
            201,
            json={
                "order_id": "ORD-PI-002",
                "stripe_id": "pi_test_xyz789",
                "payment_type": "payment_intent",
                "client_secret": "pi_test_xyz789_secret_000",
                "status": "INITIATED",
                "amount": 100.0,
                "amount_cents": 10000,
                "currency": "EUR",
                "created_at": "2026-10-15T22:00:00Z",
            },
        )

    with StripeClient("http://stripe.test", transport=httpx.MockTransport(handler)) as client:
        req = CreatePaymentIntentRequest(
            order_id="ORD-PI-002",
            amount=100.0,
            currency="EUR",
            description="Direct Payment",
        )
        pi = client.create_payment_intent(req)
        assert isinstance(pi, PaymentResponse)
        assert pi.stripe_id == "pi_test_xyz789"
        assert pi.client_secret == "pi_test_xyz789_secret_000"
        assert pi.amount == 100.0


def test_stripe_client_get_payment():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/stripe/payments/pi_test_xyz789"
        return httpx.Response(
            200,
            json={
                "order_id": "ORD-PI-002",
                "stripe_id": "pi_test_xyz789",
                "payment_type": "payment_intent",
                "status": "PAID",
                "amount": 100.0,
                "amount_cents": 10000,
                "currency": "EUR",
                "paid_at": "2026-10-15T22:02:00Z",
                "receipt_url": "https://pay.stripe.com/receipts/pi_test_xyz789",
                "created_at": "2026-10-15T22:00:00Z",
            },
        )

    with StripeClient("http://stripe.test", transport=httpx.MockTransport(handler)) as client:
        payment = client.get_payment("pi_test_xyz789")
        assert isinstance(payment, PaymentResponse)
        assert payment.status == OrderStatus.PAID
        assert payment.receipt_url.startswith("https://pay.stripe.com")


def test_stripe_client_get_payment_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"detail": "Payment pi_missing not found in Stripe adapter"}
        )

    with StripeClient("http://stripe.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PaymentNotFoundError) as exc_info:
            client.get_payment("pi_missing")
        assert exc_info.value.status_code == 404


def test_stripe_client_sync_payment():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/stripe/payments/cs_123/sync"
        return httpx.Response(
            200,
            json={
                "order_id": "ORD-1",
                "stripe_id": "cs_123",
                "previous_status": "INITIATED",
                "current_status": "PAID",
                "synced": True,
                "details": "Status synchronized from Stripe API",
            },
        )

    with StripeClient("http://stripe.test", transport=httpx.MockTransport(handler)) as client:
        sync_res = client.sync_payment("cs_123")
        assert isinstance(sync_res, SyncPaymentResponse)
        assert sync_res.current_status == OrderStatus.PAID
        assert sync_res.synced is True


def test_stripe_client_gateway_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(504, json={"detail": "Stripe API timed out after 10.0s"})

    with StripeClient("http://stripe.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PaymentTimeoutError) as exc_info:
            client.sync_payment("cs_123")
        assert exc_info.value.status_code == 504


def test_stripe_client_gateway_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"detail": "Stripe API 500 error"})

    with StripeClient("http://stripe.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PaymentGatewayError) as exc_info:
            client.get_payment("cs_123")
        assert exc_info.value.status_code == 502


def test_stripe_client_unauthorized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid or missing adapter key"})

    with StripeClient("http://stripe.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AuthenticationError) as exc_info:
            client.get_payment("cs_123")
        assert exc_info.value.status_code == 401
