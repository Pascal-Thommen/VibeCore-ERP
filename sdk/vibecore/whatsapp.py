"""Typed SDK client for the VibeCore WhatsApp Cloud API adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

import httpx


@dataclass(frozen=True, slots=True)
class WhatsAppSendResult:
    success: bool
    message_id: str | None
    recipient: str
    status: str
    is_test_mode: bool


@dataclass(frozen=True, slots=True)
class OtpSendResult:
    success: bool
    reference_id: str
    phone_number: str
    expires_at: str
    whatsapp_message_id: str | None
    test_code: str | None


@dataclass(frozen=True, slots=True)
class OtpVerificationResult:
    success: bool
    status: str
    phone_number: str
    reference_id: str | None
    verified_at: str | None
    message: str


class WhatsAppAdapterClient:
    """Connect to the WhatsApp Cloud API adapter microservice."""

    def __init__(self, base_url: str = "http://localhost:8001", timeout: float = 10.0) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
        )

    def health(self) -> dict[str, Any]:
        """Check adapter liveness."""
        res = self._client.get("/health")
        res.raise_for_status()
        return res.json()

    def send_template(
        self,
        to: str,
        template_name: str,
        language_code: str = "es",
        body_parameters: list[str] | None = None,
        button_parameters: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> WhatsAppSendResult:
        """Send a registered WhatsApp template."""
        payload = {
            "to": to,
            "template_name": template_name,
            "language_code": language_code,
            "body_parameters": body_parameters or [],
            "button_parameters": button_parameters or [],
            "meta": meta,
        }
        res = self._client.post("/api/v1/messages/send-template", json=payload)
        res.raise_for_status()
        data = res.json()
        return WhatsAppSendResult(
            success=data["success"],
            message_id=data.get("message_id"),
            recipient=data["recipient"],
            status=data["status"],
            is_test_mode=data.get("is_test_mode", False),
        )

    def send_text(
        self,
        to: str,
        message: str,
        preview_url: bool = False,
        enforce_24h_window: bool = True,
        meta: dict[str, Any] | None = None,
    ) -> WhatsAppSendResult:
        """Send free-form text inside 24h customer service window."""
        payload = {
            "to": to,
            "message": message,
            "preview_url": preview_url,
            "enforce_24h_window": enforce_24h_window,
            "meta": meta,
        }
        res = self._client.post("/api/v1/messages/send-text", json=payload)
        res.raise_for_status()
        data = res.json()
        return WhatsAppSendResult(
            success=data["success"],
            message_id=data.get("message_id"),
            recipient=data["recipient"],
            status=data["status"],
            is_test_mode=data.get("is_test_mode", False),
        )

    def request_otp(
        self,
        phone_number: str,
        purpose: str = "sso_login",
        expiry_seconds: int | None = None,
        send_via_whatsapp: bool = True,
    ) -> OtpSendResult:
        """Request single sign-on OTP generation and WhatsApp dispatch."""
        payload = {
            "phone_number": phone_number,
            "purpose": purpose,
            "expiry_seconds": expiry_seconds,
            "send_via_whatsapp": send_via_whatsapp,
        }
        res = self._client.post("/api/v1/otp/send", json=payload)
        res.raise_for_status()
        data = res.json()
        return OtpSendResult(
            success=data["success"],
            reference_id=data["reference_id"],
            phone_number=data["phone_number"],
            expires_at=data["expires_at"],
            whatsapp_message_id=data.get("whatsapp_message_id"),
            test_code=data.get("test_code"),
        )

    def verify_otp(
        self,
        phone_number: str,
        code: str,
        purpose: str = "sso_login",
    ) -> OtpVerificationResult:
        """Verify an entered OTP code."""
        payload = {
            "phone_number": phone_number,
            "code": code,
            "purpose": purpose,
        }
        res = self._client.post("/api/v1/otp/verify", json=payload)
        res.raise_for_status()
        data = res.json()
        return OtpVerificationResult(
            success=data["success"],
            status=data["status"],
            phone_number=data["phone_number"],
            reference_id=data.get("reference_id"),
            verified_at=data.get("verified_at"),
            message=data["message"],
        )

    def close(self) -> None:
        """Release underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
