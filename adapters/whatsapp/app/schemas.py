"""Pydantic schemas for the WhatsApp Cloud API adapter."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class OtpStatus(StrEnum):
    """Lifecycle status of a one-time password."""

    PENDING = "pending"
    VERIFIED = "verified"
    EXPIRED = "expired"
    INVALID_CODE = "invalid_code"
    MAX_ATTEMPTS_EXCEEDED = "max_attempts_exceeded"
    NOT_FOUND = "not_found"
    ALREADY_USED = "already_used"
    RATE_LIMITED = "rate_limited"


class MessageDeliveryStatus(StrEnum):
    """Delivery status updates from Meta."""

    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class SendTemplateRequest(BaseModel):
    """Request payload to send a pre-approved WhatsApp template message."""

    to: str = Field(description="Recipient phone number with country code")
    template_name: str = Field(description="Template name in Meta Business Manager")
    language_code: str = Field(default="es", description="Language code such as 'es' or 'en_US'")
    body_parameters: list[str] = Field(
        default_factory=list,
        description="Positional text parameters substituting {{1}}, {{2}} in template body",
    )
    button_parameters: list[str] = Field(
        default_factory=list,
        description="URL or payload parameters for template interactive buttons",
    )
    meta: dict[str, Any] | None = Field(default=None, description="Optional metadata object")
    custom_data: dict[str, Any] | None = Field(
        default=None, description="Optional custom client data"
    )


class SendTextRequest(BaseModel):
    """Request payload to send a free-form text message in the 24-hour service window."""

    to: str = Field(description="Recipient phone number with country code")
    message: str = Field(description="Body of the text message to send")
    preview_url: bool = Field(default=False, description="Preview cards for URLs")
    enforce_24h_window: bool = Field(
        default=True,
        description="Whether to fail if outside the Meta 24-hour customer service window",
    )
    meta: dict[str, Any] | None = Field(default=None, description="Optional metadata object")
    custom_data: dict[str, Any] | None = Field(
        default=None, description="Optional custom client data"
    )


class SendResponse(BaseModel):
    """Standardized delivery response from the WhatsApp adapter."""

    success: bool
    message_id: str | None = None
    recipient: str
    status: str
    is_test_mode: bool = False
    details: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class OtpGenerateRequest(BaseModel):
    """Request to generate and optionally send an OTP code via WhatsApp."""

    phone_number: str = Field(description="Target recipient phone number")
    purpose: str = Field(default="sso_login", description="Purpose tag: sso_login, etc.")
    expiry_seconds: int | None = Field(
        default=None, description="Custom expiration in seconds; defaults to configured TTL"
    )
    send_via_whatsapp: bool = Field(
        default=True, description="Whether to automatically dispatch WhatsApp message"
    )
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class OtpGenerateResponse(BaseModel):
    """Response after creating an OTP session."""

    success: bool
    reference_id: str
    phone_number: str
    expires_at: datetime
    whatsapp_message_id: str | None = None
    test_code: str | None = Field(
        default=None,
        description="Exposed only in test or development mode for automated assertions",
    )
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class OtpVerifyRequest(BaseModel):
    """Request to verify an entered OTP code."""

    phone_number: str
    code: str
    purpose: str = "sso_login"
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class OtpVerifyResponse(BaseModel):
    """Result of OTP verification."""

    success: bool
    status: OtpStatus
    phone_number: str
    reference_id: str | None = None
    verified_at: datetime | None = None
    message: str
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class ServiceWindowStatus(BaseModel):
    """Status of the Meta 24-hour customer service window for a contact."""

    phone_number: str
    is_active: bool
    last_incoming_at: datetime | None = None
    expires_at: datetime | None = None
    remaining_seconds: int = 0
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


# Meta Webhook Payloads
class MetaTextMessage(BaseModel):
    body: str


class MetaIncomingMessage(BaseModel):
    from_: str = Field(alias="from")
    id: str
    timestamp: str
    type: str = "text"
    text: MetaTextMessage | None = None


class MetaStatusUpdate(BaseModel):
    id: str
    status: str
    timestamp: str
    recipient_id: str
    errors: list[dict[str, Any]] | None = None


class MetaWebhookValue(BaseModel):
    messaging_product: str = "whatsapp"
    metadata: dict[str, Any] | None = None
    contacts: list[dict[str, Any]] | None = None
    messages: list[MetaIncomingMessage] | None = None
    statuses: list[MetaStatusUpdate] | None = None


class MetaWebhookChange(BaseModel):
    field: str
    value: MetaWebhookValue


class MetaWebhookEntry(BaseModel):
    id: str
    changes: list[MetaWebhookChange]


class MetaWebhookPayload(BaseModel):
    object: str
    entry: list[MetaWebhookEntry]


class WebhookEventAck(BaseModel):
    """Acknowledgment returned by the webhook processor."""

    success: bool
    processed_messages: int
    processed_statuses: int
