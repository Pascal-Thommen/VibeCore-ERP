"""Tests for BancardPaymentService (business logic, idempotency, state machine, rollbacks)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bancard.config import settings
from bancard.constants import (
    CURRENCY_PYG,
    RESPONSE_CODE_APPROVED,
    RESPONSE_CODE_INSUFFICIENT_FUNDS,
    PaymentMethod,
    TransactionStatus,
)
from bancard.crypto import generate_confirmation_token_confirm
from bancard.database import BancardTransaction, Base, TransactionAuditLog
from bancard.models import (
    BancardWebhookOperation,
    BancardWebhookPayload,
    CardCatastroRequest,
    CatastroQrGenerateRequest,
    SingleBuyInitRequest,
    TokenChargeRequest,
)
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


@pytest.fixture
def service():
    return BancardPaymentService()


def test_initialize_single_buy_flow(db, service):
    req = SingleBuyInitRequest(
        amount=Decimal("45000.00"),
        currency=CURRENCY_PYG,
        description="AIBill 1 Month Subscription",
        user_id="usr_pascal_01",
        idempotency_key="idemp_sb_001",
    )

    resp = service.initialize_single_buy(db=db, req=req)

    assert resp.shop_process_id >= 100001
    assert resp.status == TransactionStatus.PENDING.value
    assert resp.amount == Decimal("45000.00")
    assert resp.currency == CURRENCY_PYG
    assert len(resp.token) == 32
    assert "single_buy" in resp.checkout_url

    # Check persistence
    tx = db.query(BancardTransaction).filter(BancardTransaction.shop_process_id == resp.shop_process_id).first()
    assert tx is not None
    assert tx.idempotency_key == "idemp_sb_001"
    assert tx.payment_method == PaymentMethod.SINGLE_BUY.value
    assert tx.status == TransactionStatus.PENDING.value

    # Check audit log
    logs = db.query(TransactionAuditLog).filter(TransactionAuditLog.transaction_id == tx.id).all()
    assert len(logs) == 1
    assert logs[0].new_status == TransactionStatus.PENDING.value


def test_single_buy_idempotency(db, service):
    req = SingleBuyInitRequest(
        amount=Decimal("45000.00"),
        currency=CURRENCY_PYG,
        description="AIBill Subscription",
        user_id="usr_pascal_01",
        idempotency_key="idemp_sb_duplicate_test",
    )

    resp1 = service.initialize_single_buy(db=db, req=req)
    resp2 = service.initialize_single_buy(db=db, req=req)

    # Must return identical transaction
    assert resp1.shop_process_id == resp2.shop_process_id
    assert resp1.token == resp2.token
    assert resp1.process_id == resp2.process_id

    # Database must only contain 1 row
    tx_count = db.query(BancardTransaction).filter(BancardTransaction.idempotency_key == "idemp_sb_duplicate_test").count()
    assert tx_count == 1


def test_initialize_card_catastro(db, service):
    req = CardCatastroRequest(
        user_id="usr_pascal_01",
        card_id=1,
        user_cell_phone="+595981123456",
        user_mail="pascal@example.com",
    )

    resp = service.initialize_card_catastro(db=db, req=req)
    assert resp.user_id == "usr_pascal_01"
    assert resp.card_id == 1
    assert resp.process_id.startswith("card_proc_")


def test_execute_token_charge_approved(db, service):
    req = TokenChargeRequest(
        alias_token="alias_valid_token_123",
        amount=Decimal("45000.00"),
        currency=CURRENCY_PYG,
        description="Auto top-up",
        user_id="usr_pascal_01",
        idempotency_key="idemp_charge_001",
    )

    resp = service.execute_token_charge(db=db, req=req)
    assert resp.status == TransactionStatus.APPROVED.value
    assert resp.response_code == RESPONSE_CODE_APPROVED

    # Check audit
    tx = db.query(BancardTransaction).filter(BancardTransaction.shop_process_id == resp.shop_process_id).first()
    assert tx.status == TransactionStatus.APPROVED.value
    assert len(tx.audit_logs) >= 1


def test_execute_token_charge_idempotent(db, service):
    req = TokenChargeRequest(
        alias_token="alias_valid_token_123",
        amount=Decimal("45000.00"),
        currency=CURRENCY_PYG,
        description="Auto top-up",
        user_id="usr_pascal_01",
        idempotency_key="idemp_charge_dup",
    )

    resp1 = service.execute_token_charge(db=db, req=req)
    resp2 = service.execute_token_charge(db=db, req=req)

    assert resp1.shop_process_id == resp2.shop_process_id
    assert resp1.status == resp2.status


def test_rollback_pending_and_approved_transactions(db, service):
    # 1. Rollback a pending transaction
    sb_req = SingleBuyInitRequest(
        amount=Decimal("45000.00"),
        currency=CURRENCY_PYG,
        description="Pending purchase",
        user_id="usr_pascal_01",
    )
    sb_resp = service.initialize_single_buy(db=db, req=sb_req)

    rb_resp = service.execute_rollback(db=db, shop_process_id=sb_resp.shop_process_id, reason="Customer cancelled")
    assert rb_resp.status == TransactionStatus.REVERSED.value
    assert rb_resp.response_code == "00"

    tx = db.query(BancardTransaction).filter(BancardTransaction.shop_process_id == sb_resp.shop_process_id).first()
    assert tx.status == TransactionStatus.REVERSED.value

    # 2. Repeated rollback is idempotent
    rb_dup = service.execute_rollback(db=db, shop_process_id=sb_resp.shop_process_id)
    assert rb_dup.status == TransactionStatus.REVERSED.value

    # 3. Non-existent rollback raises ValueError
    with pytest.raises(ValueError, match="not found"):
        service.execute_rollback(db=db, shop_process_id=999999)


def test_process_bancard_confirmation_approved(db, service):
    # First create pending transaction
    sb_req = SingleBuyInitRequest(
        amount=Decimal("45000.00"),
        currency=CURRENCY_PYG,
        description="Pending checkout",
        user_id="usr_pascal_01",
    )
    sb_resp = service.initialize_single_buy(db=db, req=sb_req)

    valid_token = generate_confirmation_token_confirm(
        settings.bancard_private_key,
        sb_resp.shop_process_id,
        Decimal("45000.00"),
        CURRENCY_PYG,
    )

    webhook_payload = BancardWebhookPayload(
        operation=BancardWebhookOperation(
            token=valid_token,
            shop_process_id=sb_resp.shop_process_id,
            amount="45000.00",
            currency=CURRENCY_PYG,
            response="S",
            response_code=RESPONSE_CODE_APPROVED,
            response_description="Transaccion aprobada",
            ticket_number="TKT_888999",
            authorization_number="AUTH_123456",
        )
    )

    result = service.process_bancard_confirmation(db=db, payload=webhook_payload)
    assert result.status == "success"
    assert result.transaction_status == TransactionStatus.APPROVED.value

    tx = db.query(BancardTransaction).filter(BancardTransaction.shop_process_id == sb_resp.shop_process_id).first()
    assert tx.status == TransactionStatus.APPROVED.value
    assert tx.ticket_number == "TKT_888999"
    assert tx.authorization_number == "AUTH_123456"

    # Idempotent re-submission
    result_dup = service.process_bancard_confirmation(db=db, payload=webhook_payload)
    assert result_dup.status == "success"
    assert "already recorded" in result_dup.message


def test_process_bancard_confirmation_rejected(db, service):
    sb_req = SingleBuyInitRequest(
        amount=Decimal("45000.00"),
        currency=CURRENCY_PYG,
        description="Pending checkout",
        user_id="usr_pascal_01",
    )
    sb_resp = service.initialize_single_buy(db=db, req=sb_req)

    valid_token = generate_confirmation_token_confirm(
        settings.bancard_private_key,
        sb_resp.shop_process_id,
        Decimal("45000.00"),
        CURRENCY_PYG,
    )

    webhook_payload = BancardWebhookPayload(
        operation=BancardWebhookOperation(
            token=valid_token,
            shop_process_id=sb_resp.shop_process_id,
            amount="45000.00",
            currency=CURRENCY_PYG,
            response="F",
            response_code=RESPONSE_CODE_INSUFFICIENT_FUNDS,
            response_description="Fondos insuficientes",
        )
    )

    result = service.process_bancard_confirmation(db=db, payload=webhook_payload)
    assert result.transaction_status == TransactionStatus.REJECTED.value

    tx = db.query(BancardTransaction).filter(BancardTransaction.shop_process_id == sb_resp.shop_process_id).first()
    assert tx.status == TransactionStatus.REJECTED.value
    assert tx.response_code == RESPONSE_CODE_INSUFFICIENT_FUNDS


def test_process_bancard_confirmation_invalid_token(db, service):
    webhook_payload = BancardWebhookPayload(
        operation=BancardWebhookOperation(
            token="invalid_tampered_token",
            shop_process_id=12345,
            amount="45000.00",
            currency=CURRENCY_PYG,
            response_code=RESPONSE_CODE_APPROVED,
        )
    )

    with pytest.raises(ValueError, match="security token mismatch"):
        service.process_bancard_confirmation(db=db, payload=webhook_payload)


def test_generate_catastro_qr_and_status(db, service):
    req = CatastroQrGenerateRequest(
        amount=Decimal("45000.00"),
        currency=CURRENCY_PYG,
        description="QR payment test",
        user_id="usr_pascal_01",
        idempotency_key="idemp_qr_01",
        expires_in_minutes=15,
    )

    qr_resp = service.generate_catastro_qr(db=db, req=req)
    assert qr_resp.shop_process_id >= 100001
    assert qr_resp.qr_payload.startswith("000201")
    assert qr_resp.qr_image_data_uri.startswith("data:image/png;base64,")
    assert qr_resp.status == TransactionStatus.PENDING.value

    # Query status
    status_resp = service.get_qr_status(db=db, shop_process_id=qr_resp.shop_process_id)
    assert status_resp.status == TransactionStatus.PENDING.value
    assert status_resp.amount == Decimal("45000.00")
    assert status_resp.payment_method == PaymentMethod.CATASTRO_QR.value

    # Test expired QR status update
    tx = db.query(BancardTransaction).filter(BancardTransaction.shop_process_id == qr_resp.shop_process_id).first()
    tx.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.commit()

    expired_status = service.get_qr_status(db=db, shop_process_id=qr_resp.shop_process_id)
    assert expired_status.status == TransactionStatus.REJECTED.value
