"""Tests for Resilience, Data Integrity, Security, and Observability (4-Pillar Validation)."""

from decimal import Decimal
from unittest.mock import patch
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bancard.client import BancardGatewayClient, BancardGatewayError
from bancard.constants import PaymentMethod, TransactionStatus
from bancard.database import BancardTransaction, Base
from bancard.metrics import metrics
from bancard.models import SingleBuyInitRequest
from bancard.service import BancardPaymentService


from sqlalchemy.pool import StaticPool


@pytest.fixture
def db():
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def test_gateway_timeout_resilience():
    client = BancardGatewayClient(base_url="https://vpos.infonet.com.py:8888", timeout=0.01)

    with patch("httpx.Client.post", side_effect=httpx.TimeoutException("Read timed out")):
        with pytest.raises(BancardGatewayError) as exc_info:
            client.single_buy(1001, 45000, "PYG", "Timeout test")

        assert exc_info.value.status_code == 504
        assert "timed out" in str(exc_info.value)


def test_gateway_network_error_resilience():
    client = BancardGatewayClient(base_url="https://vpos.infonet.com.py:8888", timeout=5.0)

    with patch("httpx.Client.post", side_effect=httpx.ConnectError("Network is down")):
        with pytest.raises(BancardGatewayError) as exc_info:
            client.single_buy(1001, 45000, "PYG", "Network test")

        assert exc_info.value.status_code == 502
        assert "connectivity failure" in str(exc_info.value)


def test_gateway_error_response_handling():
    client = BancardGatewayClient(base_url="https://vpos.infonet.com.py:8888")

    error_response = httpx.Response(
        status_code=200,
        json={"status": "error", "messages": [{"key": "InvalidToken", "dsc": "Token is invalid"}]},
    )

    with patch("httpx.Client.post", return_value=error_response):
        with pytest.raises(BancardGatewayError) as exc_info:
            client.single_buy(1001, 45000, "PYG", "Error test")

        assert exc_info.value.status_code == 400
        assert "InvalidToken" in str(exc_info.value)


def test_metrics_recording_and_prom_exposition():
    initial_text = metrics.generate_prometheus_text()
    assert "bancard_transactions_total" in initial_text

    # Record test transaction
    metrics.record_transaction("APPROVED", "single_buy", 0.042)
    metrics.record_webhook_dispatch("success")
    metrics.set_dead_letter_count(0)

    updated_text = metrics.generate_prometheus_text()
    assert 'bancard_transactions_total{status="APPROVED",method="single_buy"}' in updated_text
    assert "bancard_dead_letter_total 0" in updated_text


def test_no_private_keys_in_logs_or_audit(db, service):
    req = SingleBuyInitRequest(
        amount=Decimal("45000.00"),
        currency="PYG",
        description="Private key leak check",
        user_id="usr_security_01",
    )

    resp = service.initialize_single_buy(db=db, req=req)
    tx = db.query(BancardTransaction).filter(BancardTransaction.shop_process_id == resp.shop_process_id).first()

    # Verify that raw_request and audit logs do NOT contain private key
    assert "private_key" not in str(tx.raw_request)
    for log in tx.audit_logs:
        assert "private_key" not in str(log.details)
