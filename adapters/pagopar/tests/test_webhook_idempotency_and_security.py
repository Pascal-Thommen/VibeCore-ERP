"""
Tests for Webhook security validation, idempotent processing, and replay prevention.
Säule 1 (Idempotenz) und Säule 2 (Datenintegrität) des Software Testing Audit Frameworks.
"""

from datetime import datetime, timezone
import pytest
from pagopar.client import PagoparClient, PagoparSignatureError
from pagopar.db_models import PagoparTransaction, PagoparWebhookLog
from pagopar.models import (
    OrderStatus,
    PagoparWebhookItem,
    PagoparWebhookPayload,
)
from pagopar.service import PagoparPaymentService


@pytest.fixture
def test_service(test_settings):
    client = PagoparClient(test_settings)
    return PagoparPaymentService(client=client, custom_settings=test_settings)


@pytest.fixture
def seeded_transaction(db_session):
    tx = PagoparTransaction(
        order_id="ORD-WEBHOOK-TEST",
        pagopar_hash="hash_webhook_1234567890abcdef",
        status=OrderStatus.PENDING_PAYMENT.value,
        monto_total=250000.0,
        currency="PYG",
        buyer_email="juan@empresa.py",
        buyer_ruc="1234567-8",
        buyer_name="Juan Perez",
        description="Pago de servicios",
        checkout_url="https://sandbox.pagopar.com/pagos/hash_webhook_1234567890abcdef",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(tx)
    db_session.commit()
    db_session.refresh(tx)
    return tx


def test_valid_webhook_marks_transaction_as_paid(db_session, test_service, seeded_transaction, test_settings):
    hash_pedido = seeded_transaction.pagopar_hash
    valid_token = PagoparClient.compute_webhook_token(test_settings.pagopar_private_key, hash_pedido)

    webhook_item = PagoparWebhookItem(
        pagado=True,
        fecha_pago="2026-10-15 12:00:00",
        forma_pago="Tarjeta de Credito Bancard",
        forma_pago_identificador="1",
        hash_pedido=hash_pedido,
        monto=250000.0,
        token=valid_token,
        numero_comprobante="COMP-9988",
        identificador_pago=1001,
    )
    payload = PagoparWebhookPayload(respuesta=True, resultado=[webhook_item])

    result = test_service.process_webhook(db_session, payload)
    assert result.status == "success"
    assert result.processed_count == 1

    # Verify transaction in database
    db_session.refresh(seeded_transaction)
    assert seeded_transaction.status == OrderStatus.PAID.value
    assert seeded_transaction.payment_method == "Tarjeta de Credito Bancard"
    assert seeded_transaction.receipt_number == "COMP-9988"
    assert seeded_transaction.paid_at is not None

    # Verify audit log in database
    log = db_session.query(PagoparWebhookLog).filter(PagoparWebhookLog.hash_pedido == hash_pedido).first()
    assert log is not None
    assert log.is_valid_signature is True
    assert log.processed_status == "PROCESSED"
    assert log.identificador_pago == 1001


def test_duplicate_webhook_is_processed_idempotently(db_session, test_service, seeded_transaction, test_settings):
    hash_pedido = seeded_transaction.pagopar_hash
    valid_token = PagoparClient.compute_webhook_token(test_settings.pagopar_private_key, hash_pedido)

    webhook_item = PagoparWebhookItem(
        pagado=True,
        fecha_pago="2026-10-15 12:00:00",
        forma_pago="Bancard",
        hash_pedido=hash_pedido,
        monto=250000.0,
        token=valid_token,
        numero_comprobante="COMP-9988",
        identificador_pago=2002,
    )
    payload = PagoparWebhookPayload(respuesta=True, resultado=[webhook_item])

    # First delivery
    res1 = test_service.process_webhook(db_session, payload)
    assert res1.items[0]["status"] == "PROCESSED"

    # Second delivery (replay / retry)
    res2 = test_service.process_webhook(db_session, payload)
    assert res2.items[0]["status"] == "already_processed"

    # Transaction should still be PAID without corrupted state
    db_session.refresh(seeded_transaction)
    assert seeded_transaction.status == OrderStatus.PAID.value

    # Verify second event was recorded as DUPLICATE_IGNORED
    logs = db_session.query(PagoparWebhookLog).filter(PagoparWebhookLog.hash_pedido == hash_pedido).all()
    assert len(logs) == 2
    assert logs[0].processed_status == "PROCESSED"
    assert logs[1].processed_status == "DUPLICATE_IGNORED"


def test_tampered_signature_raises_security_error_and_preserves_transaction(
    db_session, test_service, seeded_transaction
):
    hash_pedido = seeded_transaction.pagopar_hash
    tampered_token = "deadbeef1234567890deadbeef1234567890dead"

    webhook_item = PagoparWebhookItem(
        pagado=True,
        fecha_pago="2026-10-15 12:00:00",
        forma_pago="Fake Payment",
        hash_pedido=hash_pedido,
        monto=250000.0,
        token=tampered_token,
        numero_comprobante="FAKE-123",
        identificador_pago=3003,
    )
    payload = PagoparWebhookPayload(respuesta=True, resultado=[webhook_item])

    with pytest.raises(PagoparSignatureError):
        test_service.process_webhook(db_session, payload)

    # Transaction must NOT be marked as PAID
    db_session.refresh(seeded_transaction)
    assert seeded_transaction.status == OrderStatus.PENDING_PAYMENT.value
    assert seeded_transaction.paid_at is None

    # Security failure must be permanently logged for auditing
    log = db_session.query(PagoparWebhookLog).filter(PagoparWebhookLog.hash_pedido == hash_pedido).first()
    assert log is not None
    assert log.is_valid_signature is False
    assert log.processed_status == "SIGNATURE_FAILED"


def test_payment_failed_webhook_marks_transaction_failed(db_session, test_service, seeded_transaction, test_settings):
    hash_pedido = seeded_transaction.pagopar_hash
    valid_token = PagoparClient.compute_webhook_token(test_settings.pagopar_private_key, hash_pedido)

    webhook_item = PagoparWebhookItem(
        pagado=False,
        fecha_pago=None,
        forma_pago="Fondos Insuficientes",
        hash_pedido=hash_pedido,
        monto=250000.0,
        token=valid_token,
        identificador_pago=4004,
    )
    payload = PagoparWebhookPayload(respuesta=True, resultado=[webhook_item])

    test_service.process_webhook(db_session, payload)

    db_session.refresh(seeded_transaction)
    assert seeded_transaction.status == OrderStatus.FAILED.value
