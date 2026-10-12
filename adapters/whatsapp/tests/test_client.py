"""Tests for the Meta WhatsApp Cloud API client."""

import httpx
import pytest

from app.client import (
    ServiceWindowExpiredError,
    WhatsAppApiError,
    WhatsAppCloudApiClient,
)
from app.config import WhatsAppSettings
from app.schemas import SendTemplateRequest, SendTextRequest
from app.service_window import service_window_manager


def test_send_template_in_test_mode() -> None:
    cfg = WhatsAppSettings(meta_test_mode=True)
    client = WhatsAppCloudApiClient(config=cfg)

    req = SendTemplateRequest(
        to="+595 981 123 456",
        template_name="auth_code_template",
        language_code="es",
        body_parameters=["654321"],
        button_parameters=["654321"],
    )

    res = client.send_template(req)
    assert res.success
    assert res.recipient == "595981123456"
    assert res.is_test_mode
    assert res.message_id is not None
    assert res.message_id.startswith("wamid.mock_")


def test_send_text_within_and_outside_24h_window() -> None:
    cfg = WhatsAppSettings(meta_test_mode=True)
    client = WhatsAppCloudApiClient(config=cfg)
    phone = "+595 981 999 888"

    service_window_manager.clear(phone)

    # 1. Closed window: sending text must fail
    req_closed = SendTextRequest(
        to=phone,
        message="Hola estimado cliente",
        enforce_24h_window=True,
    )
    with pytest.raises(ServiceWindowExpiredError, match="24-hour customer service window"):
        client.send_text(req_closed)

    # 2. Window is opened by incoming customer message
    service_window_manager.record_incoming_message(phone)

    # 3. Open window: sending text succeeds
    res_open = client.send_text(req_closed)
    assert res_open.success
    assert res_open.recipient == "595981999888"
    assert res_open.is_test_mode


def test_send_otp_wrapper() -> None:
    cfg = WhatsAppSettings(meta_test_mode=True)
    client = WhatsAppCloudApiClient(config=cfg)

    res = client.send_otp(
        to="+1 (555) 025-4555",
        code="987654",
        template_name="sso_verification_otp",
    )
    assert res.success
    assert res.recipient == "15550254555"
    assert res.is_test_mode


def test_meta_live_api_call_mocked_transport() -> None:
    # Test real transport formatting and error handling
    def mock_handler(request: httpx.Request) -> httpx.Response:
        if "messages" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "messaging_product": "whatsapp",
                    "contacts": [{"input": "595981123456", "wa_id": "595981123456"}],
                    "messages": [{"id": "wamid.live_meta_12345"}],
                },
            )
        return httpx.Response(404)

    mock_transport = httpx.MockTransport(mock_handler)
    mock_http_client = httpx.Client(transport=mock_transport)

    cfg = WhatsAppSettings(
        meta_test_mode=False,
        meta_access_token="real_token_for_test",
        meta_phone_number_id="106540352242522",
    )
    client = WhatsAppCloudApiClient(config=cfg, http_client=mock_http_client)

    req = SendTemplateRequest(
        to="595981123456",
        template_name="invoice_ready",
        body_parameters=["FAC-001-002-0001234", "150.000 Gs"],
    )

    res = client.send_template(req)
    assert res.success
    assert res.message_id == "wamid.live_meta_12345"
    assert not res.is_test_mode


def test_meta_api_error_handling() -> None:
    def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Template does not exist in the specified language",
                    "type": "OAuthException",
                    "code": 100,
                    "error_subcode": 2388040,
                }
            },
        )

    mock_transport = httpx.MockTransport(error_handler)
    mock_http_client = httpx.Client(transport=mock_transport)

    cfg = WhatsAppSettings(
        meta_test_mode=False,
        meta_access_token="token_123",
        meta_phone_number_id="106540352242522",
    )
    client = WhatsAppCloudApiClient(config=cfg, http_client=mock_http_client)

    req = SendTemplateRequest(
        to="595981123456",
        template_name="nonexistent_template",
    )

    with pytest.raises(WhatsAppApiError) as exc_info:
        client.send_template(req)

    assert "Template does not exist" in str(exc_info.value)
    assert exc_info.value.status_code == 400
