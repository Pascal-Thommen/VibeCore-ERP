"""Meta WhatsApp Cloud API HTTP client with 24h window and sandbox support."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from app.config import WhatsAppSettings, settings
from app.schemas import SendResponse, SendTemplateRequest, SendTextRequest
from app.service_window import normalize_phone_number, service_window_manager

logger = logging.getLogger(__name__)


class ServiceWindowExpiredError(Exception):
    """Raised when attempting to send free-form text outside the 24h customer service window."""


class WhatsAppApiError(Exception):
    """Raised when Meta WhatsApp Cloud API returns an error."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class WhatsAppCloudApiClient:
    """Client for Meta's WhatsApp Cloud API messages endpoint."""

    def __init__(
        self,
        config: WhatsAppSettings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config or settings
        self._external_client = http_client

    def _get_client(self) -> httpx.Client:
        if self._external_client is not None:
            return self._external_client
        return httpx.Client(timeout=15.0)

    def _is_test_mode_or_test_number(self, phone: str) -> bool:
        normalized = normalize_phone_number(phone)
        test_numbers = [normalize_phone_number(p) for p in self.config.meta_test_phone_numbers]
        # In test mode or when targeting Meta test phone numbers or when mock token is configured
        if self.config.meta_test_mode:
            return True
        if normalized in test_numbers:
            return True
        token = self.config.get_access_token()
        if not token or token == "mock_access_token":
            return True
        return False

    def send_template(self, request: SendTemplateRequest) -> SendResponse:
        """Send a pre-approved template message via Meta WhatsApp Cloud API."""
        normalized_recipient = normalize_phone_number(request.to)

        # Build Meta template components
        components: list[dict[str, Any]] = []
        if request.body_parameters:
            components.append({
                "type": "body",
                "parameters": [
                    {"type": "text", "text": str(param)}
                    for param in request.body_parameters
                ],
            })
        if request.button_parameters:
            for idx, param in enumerate(request.button_parameters):
                components.append({
                    "type": "button",
                    "sub_type": "url",
                    "index": str(idx),
                    "parameters": [{"type": "text", "text": str(param)}],
                })

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalized_recipient,
            "type": "template",
            "template": {
                "name": request.template_name,
                "language": {"code": request.language_code},
                "components": components,
            },
        }

        # Check test mode / sandbox
        if self._is_test_mode_or_test_number(normalized_recipient):
            synthetic_id = f"wamid.mock_{uuid.uuid4().hex[:16]}"
            logger.info(
                "Test mode: Mocking template '%s' delivery to %s",
                request.template_name,
                normalized_recipient,
            )
            return SendResponse(
                success=True,
                message_id=synthetic_id,
                recipient=normalized_recipient,
                status="accepted",
                is_test_mode=True,
                details={
                    "messaging_product": "whatsapp",
                    "template": request.template_name,
                    "language": request.language_code,
                    "parameters_count": len(request.body_parameters),
                },
                meta=request.meta,
                custom_data=request.custom_data,
            )

        # Live Meta Graph API call
        endpoint = (
            f"{self.config.meta_api_base_url.rstrip('/')}/"
            f"{self.config.meta_api_version}/"
            f"{self.config.meta_phone_number_id}/messages"
        )
        token = self.config.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        client = self._get_client()
        try:
            response = client.post(endpoint, json=payload, headers=headers)
            res_json = response.json()
        except Exception as exc:
            raise WhatsAppApiError(f"HTTP transport failed: {exc}", status_code=502) from exc

        if response.status_code not in (200, 201):
            error_data = res_json.get("error", {})
            err_msg = error_data.get("message", f"Meta API error (HTTP {response.status_code})")
            raise WhatsAppApiError(err_msg, status_code=response.status_code, details=error_data)

        messages = res_json.get("messages", [])
        wamid = messages[0].get("id") if messages else None

        return SendResponse(
            success=True,
            message_id=wamid,
            recipient=normalized_recipient,
            status="sent",
            is_test_mode=False,
            details=res_json,
            meta=request.meta,
            custom_data=request.custom_data,
        )

    def send_text(self, request: SendTextRequest) -> SendResponse:
        """Send a free-form text message, validating the 24-hour customer service window."""
        normalized_recipient = normalize_phone_number(request.to)

        # Enforce Meta 24-hour customer service window
        if request.enforce_24h_window:
            is_active = service_window_manager.is_window_active(normalized_recipient)
            if not is_active:
                raise ServiceWindowExpiredError(
                    f"24-hour customer service window is closed for {normalized_recipient}. "
                    "Free-form text is restricted; pre-approved template messages must be used."
                )

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalized_recipient,
            "type": "text",
            "text": {
                "preview_url": request.preview_url,
                "body": request.message,
            },
        }

        # Check test mode
        if self._is_test_mode_or_test_number(normalized_recipient):
            synthetic_id = f"wamid.mock_{uuid.uuid4().hex[:16]}"
            logger.info("Test mode: Mocking text message to %s", normalized_recipient)
            return SendResponse(
                success=True,
                message_id=synthetic_id,
                recipient=normalized_recipient,
                status="accepted",
                is_test_mode=True,
                details={
                    "messaging_product": "whatsapp",
                    "text_length": len(request.message),
                },
                meta=request.meta,
                custom_data=request.custom_data,
            )

        endpoint = (
            f"{self.config.meta_api_base_url.rstrip('/')}/"
            f"{self.config.meta_api_version}/"
            f"{self.config.meta_phone_number_id}/messages"
        )
        token = self.config.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        client = self._get_client()
        try:
            response = client.post(endpoint, json=payload, headers=headers)
            res_json = response.json()
        except Exception as exc:
            raise WhatsAppApiError(f"HTTP transport failed: {exc}", status_code=502) from exc

        if response.status_code not in (200, 201):
            error_data = res_json.get("error", {})
            err_msg = error_data.get("message", f"Meta API error (HTTP {response.status_code})")
            raise WhatsAppApiError(err_msg, status_code=response.status_code, details=error_data)

        messages = res_json.get("messages", [])
        wamid = messages[0].get("id") if messages else None

        return SendResponse(
            success=True,
            message_id=wamid,
            recipient=normalized_recipient,
            status="sent",
            is_test_mode=False,
            details=res_json,
            meta=request.meta,
            custom_data=request.custom_data,
        )

    def send_otp(
        self,
        to: str,
        code: str,
        template_name: str | None = None,
        language_code: str = "es",
        meta: dict[str, Any] | None = None,
        custom_data: dict[str, Any] | None = None,
    ) -> SendResponse:
        """Send an authentication OTP code using the configured template."""
        target_template = template_name or self.config.otp_template_name
        request = SendTemplateRequest(
            to=to,
            template_name=target_template,
            language_code=language_code,
            body_parameters=[code],
            button_parameters=[code],
            meta=meta,
            custom_data=custom_data,
        )
        return self.send_template(request)


whatsapp_client = WhatsAppCloudApiClient()
