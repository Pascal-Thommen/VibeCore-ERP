"""VibeCore Pay: Bancard vPOS 2.0 & Catastro QR Adapter Microservice."""

from app.bancard.client import BancardGatewayClient
from app.bancard.constants import PaymentMethod, TransactionStatus
from app.bancard.crypto import (
    format_bancard_amount,
    generate_charge_token,
    generate_rollback_token,
    generate_single_buy_token,
    sign_vibecore_webhook,
    verify_bancard_confirmation_token,
    verify_vibecore_webhook_signature,
)
from app.bancard.qr import (
    build_bancard_catastro_qr_payload,
    compute_emvco_crc,
    generate_qr_image_data_uri,
    verify_emvco_qr_payload,
)
from app.bancard.service import BancardPaymentService, service

__all__ = [
    "BancardGatewayClient",
    "BancardPaymentService",
    "PaymentMethod",
    "TransactionStatus",
    "build_bancard_catastro_qr_payload",
    "compute_emvco_crc",
    "format_bancard_amount",
    "generate_charge_token",
    "generate_qr_image_data_uri",
    "generate_rollback_token",
    "generate_single_buy_token",
    "service",
    "sign_vibecore_webhook",
    "verify_bancard_confirmation_token",
    "verify_emvco_qr_payload",
    "verify_vibecore_webhook_signature",
]
