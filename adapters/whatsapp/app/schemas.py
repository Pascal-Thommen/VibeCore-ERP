"""Pydantic schemas for the VibeCore WhatsApp Cloud API adapter."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OtpStatus(StrEnum):
    """Lifecycle status of a one-time password."""

    VERIFIED = "verified"
    EXPIRED = "expired"
    INVALID_CODE = "invalid_code"
    MAX_ATTEMPTS_EXCEEDED = "max_attempts_exceeded"
    NOT_FOUND = "not_found"
    ALREADY_USED = "already_used"


class SendTemplateRequest(BaseModel):
    """Request payload to send a pre-approved WhatsApp template message."""

    model_config = ConfigDict(extra="allow")

    to: str = Field(..., min_length=6, description="Recipient phone number with country code")
    template_name: str = Field(..., min_length=1, description="Template name in Meta Business Manager")
    language_code: str = Field(default="es", description="Language code such as 'es' or 'en_US'")
    body_parameters: list[str] = Field(
        default_factory=list,
        description="Positional text parameters substituting {{1}}, {{2}} in template body",
    )
    button_parameters: list[str] = Field(
        default_factory=list,
        description="URL or OTP payload parameters for template buttons",
    )
    meta: dict[str, Any] | None = Field(default=None, description="Optional metadata object")
    custom_data: dict[str, Any] | None = Field(
        default=None, description="Optional custom client data"
    )


class SendResponse(BaseModel):
    """Standardized delivery response from the WhatsApp adapter."""

    model_config = ConfigDict(extra="allow")

    success: bool
    message_id: str | None = None
    recipient: str
    status: str
    details: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class OtpGenerateRequest(BaseModel):
    """Request to generate and transmit an OTP code via WhatsApp."""

    model_config = ConfigDict(extra="allow")

    phone_number: str = Field(..., min_length=6, description="Target recipient phone number")
    purpose: str = Field(default="sso_login", description="Purpose tag: sso_login, approval, etc.")
    expiry_seconds: int | None = Field(
        default=None, gt=0, le=3600, description="Custom expiration in seconds"
    )
    template_name: str | None = Field(
        default=None, description="Optional override for WhatsApp OTP template name"
    )
    language_code: str = Field(default="es", description="Template language code")
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class OtpGenerateResponse(BaseModel):
    """Response after creating and dispatching an OTP session."""

    model_config = ConfigDict(extra="allow")

    success: bool
    reference_id: str
    phone_number: str
    expires_at: datetime
    whatsapp_message_id: str | None = None
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class OtpVerifyRequest(BaseModel):
    """Request to verify a submitted OTP code."""

    model_config = ConfigDict(extra="allow")

    phone_number: str = Field(..., min_length=6)
    code: str = Field(..., min_length=4, max_length=10)
    purpose: str = "sso_login"
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class OtpVerifyResponse(BaseModel):
    """Result of OTP verification."""

    model_config = ConfigDict(extra="allow")

    success: bool
    status: OtpStatus
    phone_number: str
    reference_id: str | None = None
    verified_at: datetime | None = None
    message: str
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


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

    model_config = ConfigDict(extra="allow")

    success: bool
    processed_messages: int
    processed_statuses: int
    statuses: list[dict[str, Any]] = Field(default_factory=list)
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str = "healthy"
    service: str = "vibecore-whatsapp-adapter"
    version: str = "0.1.0"
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str = "ready"
    checks: dict[str, bool]
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None
