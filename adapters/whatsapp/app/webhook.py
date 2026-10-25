"""Meta WhatsApp Cloud API Webhook verification and event handler."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime
from typing import Any

from app.schemas import MetaWebhookPayload, WebhookEventAck
from app.service_window import service_window_manager

logger = logging.getLogger(__name__)


class WebhookSecurityError(Exception):
    """Raised when webhook authentication or signature verification fails."""


def verify_hub_challenge(
    mode: str | None,
    verify_token: str | None,
    challenge: str | None,
    expected_token: str,
) -> str:
    """Verify Meta's GET subscription challenge."""
    if mode != "subscribe":
        raise WebhookSecurityError(f"Invalid hub.mode: expected 'subscribe', got '{mode}'")

    if not verify_token or not hmac.compare_digest(verify_token, expected_token):
        raise WebhookSecurityError("hub.verify_token does not match configured secret")

    if challenge is None:
        raise WebhookSecurityError("hub.challenge parameter is missing")

    return challenge


def verify_meta_signature(
    raw_body: bytes,
    signature_header: str | None,
    app_secret: str,
) -> bool:
    """Verify Meta's X-Hub-Signature-256 HMAC-SHA256 signature against raw payload bytes."""
    if not signature_header:
        raise WebhookSecurityError("X-Hub-Signature-256 header is missing")

    if not signature_header.startswith("sha256="):
        raise WebhookSecurityError("Invalid signature header format: expected 'sha256=' prefix")

    expected_signature = signature_header.removeprefix("sha256=").strip()
    calculated_signature = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, calculated_signature):
        raise WebhookSecurityError("Signature mismatch: payload authentication failed")

    return True


def process_webhook_payload(payload: dict[str, Any]) -> WebhookEventAck:
    """Process incoming Meta webhook payload, update 24h windows, and record statuses."""
    processed_messages = 0
    processed_statuses = 0

    try:
        parsed = MetaWebhookPayload.model_validate(payload)
    except Exception as exc:
        logger.warning("Unrecognized webhook payload structure: %s", exc)
        return WebhookEventAck(success=True, processed_messages=0, processed_statuses=0)

    for entry in parsed.entry:
        for change in entry.changes:
            value = change.value

            # Process incoming customer messages
            if value.messages:
                for msg in value.messages:
                    sender = msg.from_
                    msg_timestamp = None
                    try:
                        ts_int = int(msg.timestamp)
                        msg_timestamp = datetime.fromtimestamp(ts_int, tz=UTC)
                    except (ValueError, TypeError):
                        msg_timestamp = datetime.now(UTC)

                    # Refresh the 24-hour customer service window
                    service_window_manager.record_incoming_message(sender, msg_timestamp)
                    processed_messages += 1

            # Process delivery status updates (sent, delivered, read, failed)
            if value.statuses:
                for status in value.statuses:
                    logger.info(
                        "WhatsApp delivery status update: recipient=%s, id=%s, status=%s",
                        status.recipient_id,
                        status.id,
                        status.status,
                    )
                    processed_statuses += 1

    return WebhookEventAck(
        success=True,
        processed_messages=processed_messages,
        processed_statuses=processed_statuses,
    )
