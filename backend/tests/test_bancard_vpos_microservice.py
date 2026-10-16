"""Backend integration tests for VibeCore Pay Bancard vPOS & Catastro QR Microservice."""

from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.bancard.client import BancardGatewayClient
from app.bancard.config import settings
from app.bancard.constants import (
    CURRENCY_CODE_PYG,
    CURRENCY_PYG,
    RESPONSE_CODE_APPROVED,
    PaymentMethod,
    TransactionStatus,
)
from app.bancard.crypto import (
    format_bancard_amount,
    generate_card_new_token,
    generate_charge_token,
    generate_confirmation_token_confirm,
    generate_rollback_token,
    generate_single_buy_token,
    sign_vibecore_webhook,
    verify_bancard_confirmation_token,
    verify_vibecore_webhook_signature,
)
from app.bancard.database import BancardTransaction, Base
from app.bancard.models import (
    BancardWebhookOperation,
    BancardWebhookPayload,
    CardCatastroRequest,
    CatastroQrGenerateRequest,
    SingleBuyInitRequest,
    TokenChargeRequest,
)
from app.bancard.qr import (
    build_bancard_catastro_qr_payload,
    compute_emvco_crc,
    generate_qr_image_data_uri,
    verify_emvco_qr_payload,
)
from app.bancard.service import BancardPaymentService


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


def test_bancard_token_generation_contract():
    priv = "priv_key_999"
    pid = 10005
    amount = 45000
    currency = "PYG"

    # Single buy
    sb_tok = generate_single_buy_token(priv, pid, amount, currency)
    assert len(sb_tok) == 32

    # Rollback
    rb_tok = generate_rollback_token(priv, pid)
    assert len(rb_tok) == 32

    # Cards new
    cn_tok = generate_card_new_token(priv, 1, "usr_1")
    assert len(cn_tok) == 32

    # Charge
    ch_tok = generate_charge_token(priv, pid, amount, currency, "alias_tok")
    assert len(ch_tok) == 32


def test_bancard_emvco_catastro_qr_contract():
    payload = build_bancard_catastro_qr_payload(
        shop_process_id=20001,
        amount=45000,
        merchant_name="VibeCore Pay",
        merchant_city="Asuncion",
    )
    assert verify_emvco_qr_payload(payload)
    assert "py.com.bancard" in payload
    assert "5303600" in payload  # Guaranies code
    img_uri = generate_qr_image_data_uri(payload)
    assert img_uri.startswith("data:image/png;base64,")


def test_bancard_end_to_end_single_buy_lifecycle(db, service):
    # 1. Initialize
    req = SingleBuyInitRequest(
        amount=Decimal("45000.00"),
        currency=CURRENCY_PYG,
        description="AIBill Subscription",
        user_id="usr_backend_test",
        idempotency_key="idemp_backend_sb_01",
    )
    resp = service.initialize_single_buy(db=db, req=req)
    assert resp.status == TransactionStatus.PENDING.value
    assert resp.shop_process_id >= 100001

    # 2. Webhook confirmation
    valid_token = generate_confirmation_token_confirm(
        settings.bancard_private_key,
        resp.shop_process_id,
        Decimal("45000.00"),
        CURRENCY_PYG,
    )
    hook_payload = BancardWebhookPayload(
        operation=BancardWebhookOperation(
            token=valid_token,
            shop_process_id=resp.shop_process_id,
            amount="45000.00",
            currency=CURRENCY_PYG,
            response="S",
            response_code=RESPONSE_CODE_APPROVED,
            response_description="Aprobado",
            ticket_number="TKT_BACKEND_01",
            authorization_number="AUTH_BACKEND_01",
        )
    )
    hook_resp = service.process_bancard_confirmation(db=db, payload=hook_payload)
    assert hook_resp.transaction_status == TransactionStatus.APPROVED.value

    # 3. Rollback
    rb_resp = service.execute_rollback(db=db, shop_process_id=resp.shop_process_id, reason="Customer refunded")
    assert rb_resp.status == TransactionStatus.REVERSED.value
