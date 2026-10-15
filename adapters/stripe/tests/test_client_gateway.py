"""
Unit tests for StripeClient HTTP transport, retries, and gateway error handling.
Säule 1 (Resilienz und Netzwerkstabilität) des Software Testing Audit Frameworks.
"""

import httpx
import pytest

from stripe_adapter.client import (
    StripeClient,
    StripeGatewayError,
    StripeNetworkTimeoutError,
)
from stripe_adapter.models import (
    CreateCheckoutSessionRequest,
    CreatePaymentIntentRequest,
    LineItemModel,
)


@pytest.mark.asyncio
async def test_create_checkout_session_success(monkeypatch, test_settings):
    expected_session_id = "cs_test_a1b2c3d4e5"
    expected_url = f"https://checkout.stripe.com/c/pay/{expected_session_id}"

    async def mock_post(client_self, url, **kwargs):
        assert "/v1/checkout/sessions" in str(url)
        headers = kwargs.get("headers", {})
        assert headers["Authorization"] == f"Bearer {test_settings.stripe_secret_key}"
        data = kwargs.get("data", {})
        assert data["mode"] == "payment"
        assert data["client_reference_id"] == "ORD-1001"
        assert data["line_items[0][price_data][unit_amount]"] == "2550"  # $25.50 -> 2550 cents
        assert data["line_items[0][price_data][currency]"] == "usd"

        return httpx.Response(
            status_code=200,
            json={
                "id": expected_session_id,
                "url": expected_url,
                "payment_status": "unpaid",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    client = StripeClient(test_settings)
    req = CreateCheckoutSessionRequest(
        order_id="ORD-1001",
        amount_total=25.50,
        currency="USD",
        description="VibeCore ERP Subscription",
        customer_email="carlos@example.com",
    )

    result = await client.create_checkout_session(req, idempotency_key="idemp_1001")
    assert result["session_id"] == expected_session_id
    assert result["checkout_url"] == expected_url
    assert result["payment_status"] == "unpaid"


@pytest.mark.asyncio
async def test_create_checkout_session_with_itemized_lines(monkeypatch, test_settings):
    async def mock_post(client_self, url, **kwargs):
        data = kwargs.get("data", {})
        assert data["line_items[0][price_data][unit_amount]"] == "1000"
        assert data["line_items[0][price_data][product_data][name]"] == "Base License"
        assert data["line_items[1][price_data][unit_amount]"] == "500"
        assert data["line_items[1][price_data][product_data][name]"] == "Support Package"

        return httpx.Response(
            status_code=200,
            json={
                "id": "cs_test_items",
                "url": "https://checkout.stripe.com/c/pay/cs_test_items",
                "payment_status": "unpaid",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    client = StripeClient(test_settings)
    req = CreateCheckoutSessionRequest(
        order_id="ORD-ITEMS",
        amount_total=15.00,
        currency="USD",
        description="ERP License and Support",
        customer_email="carlos@example.com",
        items=[
            LineItemModel(name="Base License", amount=10.00, quantity=1),
            LineItemModel(name="Support Package", amount=5.00, quantity=1),
        ],
    )

    result = await client.create_checkout_session(req)
    assert result["session_id"] == "cs_test_items"


@pytest.mark.asyncio
async def test_create_payment_intent_success(monkeypatch, test_settings):
    expected_pi_id = "pi_3Ntest12345"
    expected_client_secret = f"{expected_pi_id}_secret_abc"

    async def mock_post(client_self, url, **kwargs):
        assert "/v1/payment_intents" in str(url)
        data = kwargs.get("data", {})
        assert data["amount"] == "4990"  # $49.90 -> 4990 cents
        assert data["currency"] == "usd"
        assert data["metadata[order_id]"] == "ORD-2002"

        return httpx.Response(
            status_code=200,
            json={
                "id": expected_pi_id,
                "client_secret": expected_client_secret,
                "status": "requires_payment_method",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    client = StripeClient(test_settings)
    req = CreatePaymentIntentRequest(
        order_id="ORD-2002",
        amount=49.90,
        currency="USD",
        description="Direct API Charge",
        customer_email="client@example.com",
    )

    result = await client.create_payment_intent(req)
    assert result["payment_intent_id"] == expected_pi_id
    assert result["client_secret"] == expected_client_secret
    assert result["status"] == "requires_payment_method"


@pytest.mark.asyncio
async def test_get_checkout_session_and_intent(monkeypatch, test_settings):
    async def mock_get(client_self, url, **kwargs):
        if "checkout/sessions" in str(url):
            return httpx.Response(status_code=200, json={"id": "cs_poll", "payment_status": "paid"})
        if "payment_intents" in str(url):
            return httpx.Response(status_code=200, json={"id": "pi_poll", "status": "succeeded"})
        return httpx.Response(status_code=404, json={})

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    client = StripeClient(test_settings)
    session_data = await client.get_checkout_session("cs_poll")
    assert session_data["payment_status"] == "paid"

    intent_data = await client.get_payment_intent("pi_poll")
    assert intent_data["status"] == "succeeded"


@pytest.mark.asyncio
async def test_stripe_gateway_rejection_400(monkeypatch, test_settings):
    async def mock_post(client_self, url, **kwargs):
        return httpx.Response(
            status_code=400,
            json={"error": {"message": "Invalid card number or expired payment method", "type": "card_error"}},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    client = StripeClient(test_settings)
    req = CreatePaymentIntentRequest(
        order_id="ORD-FAIL",
        amount=10.00,
        currency="USD",
        description="Test Fail",
    )

    with pytest.raises(StripeGatewayError) as exc_info:
        await client.create_payment_intent(req)

    assert "Invalid card number" in str(exc_info.value)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_stripe_server_error_retry_and_failure(monkeypatch, test_settings):
    attempts = 0

    async def mock_post(client_self, url, **kwargs):
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code=503, text="Service Unavailable")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    client = StripeClient(test_settings)
    req = CreatePaymentIntentRequest(
        order_id="ORD-503",
        amount=10.00,
        currency="USD",
        description="Test 503",
    )

    with pytest.raises(StripeGatewayError) as exc_info:
        await client.create_payment_intent(req)

    assert attempts == test_settings.max_retries
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_stripe_network_timeout_retry(monkeypatch, test_settings):
    attempts = 0

    async def mock_post(client_self, url, **kwargs):
        nonlocal attempts
        attempts += 1
        raise httpx.TimeoutException("Connection timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    client = StripeClient(test_settings)
    req = CreateCheckoutSessionRequest(
        order_id="ORD-TIMEOUT",
        amount_total=10.00,
        currency="USD",
        description="Test Timeout",
        customer_email="carlos@example.com",
    )

    with pytest.raises(StripeNetworkTimeoutError) as exc_info:
        await client.create_checkout_session(req)

    assert attempts == test_settings.max_retries
    assert "timed out" in str(exc_info.value)
