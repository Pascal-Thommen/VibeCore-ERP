"""Meta WhatsApp Cloud API Webhook verification and event handler."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from app.schemas import MetaWebhookPayload, WebhookEventAck

logger = logging.getLogger(__name__)


class WebhookSecurityError(Exception):
    """Raised when webhook authentication or HMAC signature verification fails."""


def verify_hub_challenge(
    mode: str | None,
    verify_token: str | None,
    challenge: str | None,
    expected_token: str,
) -> str:
    """Verify Meta's GET subscription challenge."""
    if mode != "subscribe":
        raise WebhookSecurityError(f"Invalid hub.mode: expected 'subscribe', got '{mode}'")

    if not expected_token or not verify_token or not hmac.compare_digest(verify_token, expected_token):
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
    if not app_secret:
        raise WebhookSecurityError("Webhook app secret is not configured")

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
    """Process incoming Meta webhook payload and extract delivery status updates."""
    processed_messages = 0
    processed_statuses = 0
    statuses_out: list[dict[str, Any]] = []

    try:
        parsed = MetaWebhookPayload.model_validate(payload)
    except Exception as exc:
        logger.warning("Unrecognized webhook payload structure: %s", exc)
        return WebhookEventAck(
            success=True,
            processed_messages=0,
            processed_statuses=0,
            statuses=[],
        )

    for entry in parsed.entry:
        for change in entry.changes:
            value = change.value

            if value.messages:
                processed_messages += len(value.messages)

            if value.statuses:
                for st in value.statuses:
                    processed_statuses += 1
                    statuses_out.append(
                        {
                            "message_id": st.id,
                            "status": st.status,
                            "recipient_id": st.recipient_id,
                            "timestamp": st.timestamp,
                        }
                    )

    return WebhookEventAck(
        success=True,
        processed_messages=processed_messages,
        processed_statuses=processed_statuses,
        statuses=statuses_out,
    )
