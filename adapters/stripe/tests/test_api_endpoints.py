"""
Tests for FastAPI REST endpoints of the Stripe Payment Gateway Adapter.
Säule 3 (Sicherheit) und Säule 4 (Observability) des Software Testing Audit Frameworks.
"""

import httpx
from fastapi.testclient import TestClient
from stripe_adapter.models import OrderStatus


def test_health_check_endpoint(test_client: TestClient):
    resp = test_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "stripe-adapter"
    assert data["version"] == "1.0.0"
    assert "X-Correlation-ID" in resp.headers
    assert "X-Process-Time" in resp.headers


def test_readiness_check_endpoint(test_client: TestClient):
    resp = test_client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is True
    assert data["database"] == "connected"
    assert data["gateway_configured"] is True


def test_create_checkout_session_api(monkeypatch, test_client: TestClient):
    async def mock_post(client_self, url, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "id": "cs_test_api_999",
                "url": "https://checkout.stripe.com/c/pay/cs_test_api_999",
                "payment_status": "unpaid",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    payload = {
        "order_id": "ORD-API-001",
        "amount_total": 55.00,
        "currency": "USD",
        "description": "API Test Checkout Session",
        "customer_email": "tester@example.com",
    }

    resp = test_client.post(
        "/api/v1/stripe/checkout-sessions",
        json=payload,
        headers={"X-Correlation-ID": "test-corr-123"},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["order_id"] == "ORD-API-001"
    assert data["stripe_id"] == "cs_test_api_999"
    assert data["checkout_url"] == "https://checkout.stripe.com/c/pay/cs_test_api_999"
    assert data["status"] == OrderStatus.PENDING_PAYMENT.value
    assert data["amount"] == 55.00
    assert data["amount_cents"] == 5500
    assert resp.headers.get("X-Correlation-ID") == "test-corr-123"


def test_create_payment_intent_api(monkeypatch, test_client: TestClient):
    async def mock_post(client_self, url, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "id": "pi_test_api_888",
                "client_secret": "pi_test_api_888_secret_xyz",
                "status": "requires_payment_method",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    payload = {
        "order_id": "ORD-API-002",
        "amount": 120.00,
        "currency": "EUR",
        "description": "API Test Direct Payment Intent",
        "customer_email": "tester2@example.com",
    }

    resp = test_client.post("/api/v1/stripe/payment-intents", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["order_id"] == "ORD-API-002"
    assert data["stripe_id"] == "pi_test_api_888"
    assert data["client_secret"] == "pi_test_api_888_secret_xyz"
    assert data["amount"] == 120.00
    assert data["amount_cents"] == 12000
    assert data["currency"] == "EUR"


def test_get_payment_not_found(test_client: TestClient):
    resp = test_client.get("/api/v1/stripe/payments/NON_EXISTENT_ORD")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_get_and_sync_payment_api(monkeypatch, test_client: TestClient):
    # 1. Create order
    async def mock_post(client_self, url, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "id": "cs_test_sync_777",
                "url": "https://checkout.stripe.com/c/pay/cs_test_sync_777",
                "payment_status": "unpaid",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    resp_create = test_client.post(
        "/api/v1/stripe/checkout-sessions",
        json={
            "order_id": "ORD-SYNC-001",
            "amount_total": 30.00,
            "currency": "USD",
            "description": "Sync Test",
            "customer_email": "sync@example.com",
        },
    )
    assert resp_create.status_code == 201

    # 2. Get payment by order_id
    resp_get = test_client.get("/api/v1/stripe/payments/ORD-SYNC-001")
    assert resp_get.status_code == 200
    assert resp_get.json()["status"] == OrderStatus.PENDING_PAYMENT.value

    # 3. Mock polling response from Stripe indicating payment is paid
    async def mock_get(client_self, url, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "id": "cs_test_sync_777",
                "payment_status": "paid",
                "payment_intent": "pi_synced_intent_123",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    resp_sync = test_client.post("/api/v1/stripe/payments/ORD-SYNC-001/sync")
    assert resp_sync.status_code == 200
    sync_data = resp_sync.json()
    assert sync_data["synced"] is True
    assert sync_data["previous_status"] == OrderStatus.PENDING_PAYMENT.value
    assert sync_data["current_status"] == OrderStatus.PAID.value

    # 4. Confirm updated state on GET
    resp_get_after = test_client.get("/api/v1/stripe/payments/cs_test_sync_777")
    assert resp_get_after.status_code == 200
    assert resp_get_after.json()["status"] == OrderStatus.PAID.value


def test_adapter_api_key_authentication(monkeypatch, test_client: TestClient, test_settings):
    import stripe_adapter.router as router_module
    from stripe_adapter.config import Settings

    auth_settings = Settings(
        adapter_api_key="secret_adapter_token_42",
        database_url="sqlite:///:memory:",
    )
    router_module.settings = auth_settings

    # Without auth header -> 401
    resp_unauth = test_client.get("/api/v1/stripe/payments/ORD-1")
    assert resp_unauth.status_code == 401

    # With invalid key -> 401
    resp_invalid = test_client.get(
        "/api/v1/stripe/payments/ORD-1",
        headers={"X-Adapter-Key": "wrong_token"},
    )
    assert resp_invalid.status_code == 401

    # With valid X-Adapter-Key -> 404 (Auth passed, proceeds to query)
    resp_valid = test_client.get(
        "/api/v1/stripe/payments/ORD-1",
        headers={"X-Adapter-Key": "secret_adapter_token_42"},
    )
    assert resp_valid.status_code == 404

    # With valid Bearer token -> 404
    resp_bearer = test_client.get(
        "/api/v1/stripe/payments/ORD-1",
        headers={"Authorization": "Bearer secret_adapter_token_42"},
    )
    assert resp_bearer.status_code == 404

    # Restore settings
    router_module.settings = test_settings
