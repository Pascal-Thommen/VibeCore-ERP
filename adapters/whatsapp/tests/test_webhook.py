"""Tests for Meta WhatsApp webhook challenge verification and event parsing."""

import hashlib
import hmac
from datetime import UTC, datetime

import pytest

from app.schemas import WebhookEventAck
from app.service_window import service_window_manager
from app.webhook import (
    WebhookSecurityError,
    process_webhook_payload,
    verify_hub_challenge,
    verify_meta_signature,
)


def test_verify_hub_challenge_success() -> None:
    expected_token = "my_meta_secret_token"
    challenge = "1158201444"

    result = verify_hub_challenge(
        mode="subscribe",
        verify_token=expected_token,
        challenge=challenge,
        expected_token=expected_token,
    )
    assert result == challenge


def test_verify_hub_challenge_invalid_token() -> None:
    expected_token = "my_meta_secret_token"
    with pytest.raises(WebhookSecurityError, match="verify_token does not match"):
        verify_hub_challenge(
            mode="subscribe",
            verify_token="wrong_token",
            challenge="12345",
            expected_token=expected_token,
        )


def test_verify_hub_challenge_invalid_mode() -> None:
    expected_token = "my_meta_secret_token"
    with pytest.raises(WebhookSecurityError, match="Invalid hub.mode"):
        verify_hub_challenge(
            mode="unsubscribe",
            verify_token=expected_token,
            challenge="12345",
            expected_token=expected_token,
        )


def test_verify_meta_signature_valid_and_invalid() -> None:
    app_secret = "meta_app_secret_abc123"
    body = b'{"object":"whatsapp_business_account"}'

    # Valid signature
    digest = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    valid_header = f"sha256={digest}"

    assert verify_meta_signature(body, valid_header, app_secret)

    # Invalid signature
    with pytest.raises(WebhookSecurityError, match="Signature mismatch"):
        verify_meta_signature(body, "sha256=invalidhexdigest123456", app_secret)

    # Missing signature
    with pytest.raises(WebhookSecurityError, match="header is missing"):
        verify_meta_signature(body, None, app_secret)

    # Malformed prefix
    with pytest.raises(WebhookSecurityError, match="expected 'sha256=' prefix"):
        verify_meta_signature(body, digest, app_secret)


def test_process_webhook_incoming_message_opens_service_window() -> None:
    phone = "595981445566"
    service_window_manager.clear(phone)
    assert not service_window_manager.is_window_active(phone)

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550254555",
                                "phone_number_id": "106540352242522",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Carlos Gomez"},
                                    "wa_id": phone,
                                }
                            ],
                            "messages": [
                                {
                                    "from": phone,
                                    "id": "wamid.HBgLM...",
                                    "timestamp": str(int(datetime.now(UTC).timestamp())),
                                    "text": {"body": "Hola, necesito mi factura"},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    ack: WebhookEventAck = process_webhook_payload(payload)
    assert ack.success
    assert ack.processed_messages == 1
    assert ack.processed_statuses == 0

    # Service window is now open!
    assert service_window_manager.is_window_active(phone)


def test_process_webhook_delivery_status_update() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550254555",
                                "phone_number_id": "106540352242522",
                            },
                            "statuses": [
                                {
                                    "id": "wamid.HBgLM...",
                                    "status": "delivered",
                                    "timestamp": "1728734450",
                                    "recipient_id": "595981445566",
                                    "conversation": {
                                        "id": "conv_123",
                                        "origin": {"type": "authentication"},
                                    },
                                    "pricing": {
                                        "billable": True,
                                        "pricing_model": "CBP",
                                        "category": "authentication",
                                    },
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    ack: WebhookEventAck = process_webhook_payload(payload)
    assert ack.success
    assert ack.processed_messages == 0
    assert ack.processed_statuses == 1
