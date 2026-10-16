"""Integration tests for Bancard FastAPI endpoints."""

from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bancard.app import app
from bancard.config import settings
from bancard.constants import CURRENCY_PYG, RESPONSE_CODE_APPROVED
from bancard.crypto import generate_confirmation_token_confirm
from bancard.database import Base, DeadLetterWebhook, get_db


from sqlalchemy.pool import StaticPool


@pytest.fixture
def client_and_db():
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    from bancard.service import service
    from tests.conftest import MockBancardGatewayClient

    orig_client = service.client
    mock_client = MockBancardGatewayClient()
    service.client = mock_client

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, TestingSession()
    service.client = orig_client
    app.dependency_overrides.clear()


def test_healthz_and_readiness(client_and_db):
    client, _ = client_and_db
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "vibecore-pay-bancard"
    assert data["database"] == "connected"

    # Also /health and /ready aliases
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


def test_prometheus_metrics_endpoint(client_and_db):
    client, _ = client_and_db
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "bancard_transactions_total" in resp.text
    assert "bancard_payment_latency_seconds" in resp.text


def test_correlation_id_middleware(client_and_db):
    client, _ = client_and_db
    resp = client.get("/healthz", headers={"X-Correlation-ID": "corr_test_12345"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Correlation-ID") == "corr_test_12345"


def test_single_buy_endpoint_lifecycle(client_and_db):
    client, _ = client_and_db
    payload = {
        "amount": 45000.0,
        "currency": "PYG",
        "description": "LiteLLM Standard Tier",
        "user_id": "usr_pascal",
    }
    resp = client.post(
        "/api/v1/payments/single-buy",
        json=payload,
        headers={"Idempotency-Key": "idemp_api_sb_01"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "PENDING"
    assert data["shop_process_id"] >= 100001
    assert "checkout_url" in data
    assert len(data["token"]) == 32

    # Query transaction
    tx_resp = client.get(f"/api/v1/payments/{data['shop_process_id']}")
    assert tx_resp.status_code == 200
    tx_data = tx_resp.json()
    assert tx_data["shop_process_id"] == data["shop_process_id"]
    assert tx_data["status"] == "PENDING"
    assert len(tx_data["audit_logs"]) >= 1


def test_card_catastro_and_charge_endpoint(client_and_db):
    client, _ = client_and_db
    # 1. Cards new
    card_resp = client.post(
        "/api/v1/payments/cards/new",
        json={
            "user_id": "usr_test_catastro",
            "card_id": 1,
            "user_mail": "test@vibecore.local",
        },
    )
    assert card_resp.status_code == 201
    assert "process_id" in card_resp.json()

    # 2. Token charge
    charge_resp = client.post(
        "/api/v1/payments/charge",
        json={
            "alias_token": "alias_catastro_tok_1",
            "amount": 75000.0,
            "currency": "PYG",
            "description": "Subscription 1-click",
            "user_id": "usr_test_catastro",
        },
        headers={"Idempotency-Key": "idemp_api_charge_01"},
    )
    assert charge_resp.status_code == 200
    c_data = charge_resp.json()
    assert c_data["status"] in ["APPROVED", "REJECTED"]


def test_rollback_endpoint(client_and_db):
    client, _ = client_and_db
    # Create single buy
    sb_resp = client.post(
        "/api/v1/payments/single-buy",
        json={"amount": 45000.0, "currency": "PYG", "description": "To rollback"},
    )
    shop_id = sb_resp.json()["shop_process_id"]

    # Execute rollback
    rb_resp = client.post(
        f"/api/v1/payments/{shop_id}/rollback",
        json={"reason": "User clicked cancel"},
    )
    assert rb_resp.status_code == 200
    assert rb_resp.json()["status"] == "REVERSED"

    # Verify transaction status changed
    tx_resp = client.get(f"/api/v1/payments/{shop_id}")
    assert tx_resp.json()["status"] == "REVERSED"


def test_bancard_webhook_confirmation_endpoint(client_and_db):
    client, _ = client_and_db
    # Initialize order
    sb_resp = client.post(
        "/api/v1/payments/single-buy",
        json={"amount": 45000.0, "currency": "PYG", "description": "Webhook order"},
    )
    shop_id = sb_resp.json()["shop_process_id"]

    valid_token = generate_confirmation_token_confirm(
        settings.bancard_private_key,
        shop_id,
        Decimal("45000.00"),
        CURRENCY_PYG,
    )

    # Valid confirmation webhook
    hook_resp = client.post(
        "/api/v1/payments/webhook/bancard",
        json={
            "operation": {
                "token": valid_token,
                "shop_process_id": shop_id,
                "amount": "45000.00",
                "currency": "PYG",
                "response": "S",
                "response_code": RESPONSE_CODE_APPROVED,
                "response_description": "Aprobado",
                "ticket_number": "TKT_123",
                "authorization_number": "AUTH_456",
            }
        },
    )
    assert hook_resp.status_code == 200
    assert hook_resp.json()["status"] == "success"
    assert hook_resp.json()["transaction_status"] == "APPROVED"

    # Invalid token rejected with 401
    bad_hook_resp = client.post(
        "/api/v1/payments/webhook/bancard",
        json={
            "operation": {
                "token": "tampered_token",
                "shop_process_id": shop_id,
                "amount": "45000.00",
                "currency": "PYG",
                "response_code": "00",
            }
        },
    )
    assert bad_hook_resp.status_code == 401


def test_catastro_qr_endpoints(client_and_db):
    client, _ = client_and_db
    qr_resp = client.post(
        "/api/v1/qr/generate",
        json={
            "amount": 45000.0,
            "currency": "PYG",
            "description": "Scan to Pay Bancard",
            "user_id": "usr_qr_client",
        },
    )
    assert qr_resp.status_code == 201
    data = qr_resp.json()
    assert data["qr_payload"].startswith("000201")
    assert data["qr_image_data_uri"].startswith("data:image/png;base64,")
    shop_id = data["shop_process_id"]

    # Poll status
    st_resp = client.get(f"/api/v1/qr/{shop_id}/status")
    assert st_resp.status_code == 200
    assert st_resp.json()["status"] == "PENDING"


def test_dead_letter_endpoints(client_and_db):
    client, db = client_and_db

    # Insert a dummy failed dead letter
    dl = DeadLetterWebhook(
        target_url="http://dead-endpoint.local",
        event_type="payment.bancard.approved",
        payload='{"test":true}',
        signature="t=1,v1=abc",
        attempts=3,
        status="FAILED",
    )
    db.add(dl)
    db.commit()

    resp = client.get("/api/v1/webhooks/dead-letter")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    assert items[0]["target_url"] == "http://dead-endpoint.local"


def test_api_not_found_and_error_paths(client_and_db):
    client, _ = client_and_db
    # Non existent transaction
    assert client.get("/api/v1/payments/999999").status_code == 404
    # Non existent QR
    assert client.get("/api/v1/qr/999999/status").status_code == 404
    # Rollback non-existent
    assert client.post("/api/v1/payments/999999/rollback", json={}).status_code == 400
    # Retry non-existent dead letter
    assert client.post("/api/v1/webhooks/dead-letter/non-existent-id/retry").status_code == 502
