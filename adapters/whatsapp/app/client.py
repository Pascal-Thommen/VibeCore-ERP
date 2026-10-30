"""Meta WhatsApp Cloud API async HTTP client with explicit timeouts and error handling."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import WhatsAppSettings, settings
from app.otp import normalize_phone_number
from app.schemas import SendResponse, SendTemplateRequest


class WhatsAppApiError(Exception):
    """Raised when Meta WhatsApp Cloud API returns an error or network failure."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class WhatsAppTimeoutError(WhatsAppApiError):
    """Raised when Meta WhatsApp Cloud API request times out (Säule 1)."""

    def __init__(self, message: str = "Timeout contacting Meta WhatsApp Cloud API") -> None:
        super().__init__(message=message, status_code=504)


class WhatsAppCloudApiClient:
    """Async client for Meta's WhatsApp Cloud API messages endpoint."""

    def __init__(
        self,
        config: WhatsAppSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config or settings
        self._http_client = http_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is not None and not self._http_client.is_closed:
            return self._http_client
        timeout = httpx.Timeout(
            connect=5.0,
            read=self.config.http_timeout_seconds,
            write=5.0,
            pool=5.0,
        )
        return httpx.AsyncClient(timeout=timeout)

    def build_template_payload(self, request: SendTemplateRequest) -> dict[str, Any]:
        """Construct the exact Meta Graph API template message JSON payload."""
        normalized_recipient = normalize_phone_number(request.to)
        components: list[dict[str, Any]] = []

        if request.body_parameters:
            components.append(
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": str(param)}
                        for param in request.body_parameters
                    ],
                }
            )

        if request.button_parameters:
            for idx, param in enumerate(request.button_parameters):
                components.append(
                    {
                        "type": "button",
                        "sub_type": "url",
                        "index": str(idx),
                        "parameters": [{"type": "text", "text": str(param)}],
                    }
                )

        return {
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

    async def send_template(self, request: SendTemplateRequest) -> SendResponse:
        """Send a pre-approved template message via Meta WhatsApp Cloud API."""
        token = self.config.get_access_token()
        if not token:
            raise WhatsAppApiError(
                "WhatsApp access token is not configured",
                status_code=401,
            )

        payload = self.build_template_payload(request)
        normalized_recipient = payload["to"]
        endpoint = (
            f"{self.config.meta_api_base_url.rstrip('/')}/"
            f"{self.config.meta_api_version}/"
            f"{self.config.meta_phone_number_id}/messages"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        client = await self._get_client()
        owns_client = client is not self._http_client

        try:
            response = await client.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=self.config.http_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise WhatsAppTimeoutError(
                f"Meta WhatsApp Cloud API timed out after {self.config.http_timeout_seconds}s"
            ) from exc
        except httpx.RequestError as exc:
            raise WhatsAppApiError(
                f"Network error contacting Meta WhatsApp Cloud API: {exc}",
                status_code=502,
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

        try:
            res_json = response.json()
        except ValueError:
            res_json = {}

        if response.status_code not in (200, 201):
            error_data = res_json.get("error", {}) if isinstance(res_json, dict) else {}
            err_msg = error_data.get(
                "message", f"Meta API error (HTTP {response.status_code})"
            )
            mapped_status = 502 if response.status_code >= 500 else response.status_code
            raise WhatsAppApiError(
                err_msg,
                status_code=mapped_status,
                details=error_data if isinstance(error_data, dict) else {},
            )

        messages = res_json.get("messages", []) if isinstance(res_json, dict) else []
        wamid = messages[0].get("id") if messages and isinstance(messages[0], dict) else None

        return SendResponse(
            success=True,
            message_id=wamid,
            recipient=normalized_recipient,
            status="sent",
            details=res_json if isinstance(res_json, dict) else None,
            meta=request.meta,
            custom_data=request.custom_data,
        )

    async def send_otp(
        self,
        to: str,
        code: str,
        template_name: str | None = None,
        language_code: str = "es",
        meta: dict[str, Any] | None = None,
        custom_data: dict[str, Any] | None = None,
    ) -> SendResponse:
        """Send an authentication OTP code using the configured WhatsApp template."""
        target_template = template_name or self.config.otp_template_name
        request = SendTemplateRequest(
            to=to,
            template_name=target_template,
            language_code=language_code or self.config.otp_template_language,
            body_parameters=[code],
            button_parameters=[code],
            meta=meta,
            custom_data=custom_data,
        )
        return await self.send_template(request)
