"""Comprehensive tests for the VibeCore WhatsApp Cloud API Microservice Adapter."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta

import httpx
import pytest
from app.client import WhatsAppApiError, WhatsAppCloudApiClient, WhatsAppTimeoutError
from app.config import WhatsAppSettings, settings
from app.main import app, get_otp_manager, get_whatsapp_client
from app.otp import OtpManager
from app.schemas import OtpStatus, SendTemplateRequest
from app.webhook import (
    WebhookSecurityError,
    process_webhook_payload,
    verify_hub_challenge,
    verify_meta_signature,
)
from fastapi.testclient import TestClient
from pydantic import SecretStr


@pytest.fixture
def test_settings() -> WhatsAppSettings:
    return WhatsAppSettings(
        meta_api_base_url="https://graph.facebook.com",
        meta_api_version="v21.0",
        meta_phone_number_id="106540352242522",
        meta_access_token=SecretStr("real-test-meta-token-xyz"),
        meta_app_secret=SecretStr("real-test-meta-app-secret-32bytes"),
        meta_webhook_verify_token=SecretStr("real-test-verify-token"),
        http_timeout_seconds=5.0,
    )


def test_health_and_ready_endpoints() -> None:
    with TestClient(app) as client:
        res_health = client.get("/health")
        assert res_health.status_code == 200
        data = res_health.json()
        assert data["status"] == "healthy"
        assert data["service"] == "vibecore-whatsapp-adapter"

        res_ready = client.get("/ready")
        assert res_ready.status_code == 200
        ready_data = res_ready.json()
        assert ready_data["status"] == "ready"
        assert ready_data["checks"]["access_token"] is True
        assert ready_data["checks"]["app_secret"] is True


def test_removed_superfluous_endpoints_return_404() -> None:
    """Ensure superfluous chat window and duplicate health endpoints are removed."""
    with TestClient(app) as client:
        assert client.get("/api/v1/service-window/595981123456").status_code == 404
        assert client.post("/api/v1/messages/send-text", json={}).status_code == 404
        assert client.get("/api/v1/health").status_code == 404
        assert client.get("/api/v1/ready").status_code == 404


@pytest.mark.asyncio
async def test_semantic_template_payload_and_response(test_settings: WhatsAppSettings) -> None:
    """Verify exact Meta Graph API JSON payload structure and response mapping."""
    captured_requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "messaging_product": "whatsapp",
                "contacts": [{"input": "595981123456", "wa_id": "595981123456"}],
                "messages": [{"id": "wamid.HBgLNTk1OTgxMTIzNDU2FQIAERgSQkI"}],
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        wa_client = WhatsAppCloudApiClient(config=test_settings, http_client=http_client)
        req = SendTemplateRequest(
            to="+595 981 123-456",
            template_name="invoice_notification",
            language_code="es",
            body_parameters=["FAC-001-002-0001234", "1.500.000 PYG"],
            button_parameters=["https://vibecore.py/invoices/1234"],
            meta={"trace_id": "tr_001"},
            custom_data={"document_id": "doc_1234"},
        )
        res = await wa_client.send_template(req)

    assert res.success is True
    assert res.message_id == "wamid.HBgLNTk1OTgxMTIzNDU2FQIAERgSQkI"
    assert res.recipient == "595981123456"
    assert res.status == "sent"
    assert res.meta == {"trace_id": "tr_001"}
    assert res.custom_data == {"document_id": "doc_1234"}

    assert len(captured_requests) == 1
    sent_req = captured_requests[0]
    assert str(sent_req.url) == "https://graph.facebook.com/v21.0/106540352242522/messages"
    assert sent_req.headers["Authorization"] == "Bearer real-test-meta-token-xyz"

    sent_body = json.loads(sent_req.content.decode("utf-8"))
    assert sent_body == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "595981123456",
        "type": "template",
        "template": {
            "name": "invoice_notification",
            "language": {"code": "es"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "FAC-001-002-0001234"},
                        {"type": "text", "text": "1.500.000 PYG"},
                    ],
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [
                        {"type": "text", "text": "https://vibecore.py/invoices/1234"}
                    ],
                },
            ],
        },
    }


@pytest.mark.asyncio
async def test_client_timeout_and_provider_errors(test_settings: WhatsAppSettings) -> None:
    """Verify timeout (504), network error (502), and invalid credentials (401)."""
    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Meta Graph API read timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler)) as http_client:
        wa_client = WhatsAppCloudApiClient(config=test_settings, http_client=http_client)
        with pytest.raises(WhatsAppTimeoutError) as exc_info:
            await wa_client.send_template(
                SendTemplateRequest(to="+595981123456", template_name="test_tpl")
            )
        assert exc_info.value.status_code == 504

    async def net_error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection reset by peer")

    async with httpx.AsyncClient(transport=httpx.MockTransport(net_error_handler)) as http_client:
        wa_client = WhatsAppCloudApiClient(config=test_settings, http_client=http_client)
        with pytest.raises(WhatsAppApiError) as exc_info:
            await wa_client.send_template(
                SendTemplateRequest(to="+595981123456", template_name="test_tpl")
            )
        assert exc_info.value.status_code == 502

    async def auth_error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "error": {
                    "message": "Invalid OAuth access token.",
                    "type": "OAuthException",
                    "code": 190,
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(auth_error_handler)) as http_client:
        wa_client = WhatsAppCloudApiClient(config=test_settings, http_client=http_client)
        with pytest.raises(WhatsAppApiError) as exc_info:
            await wa_client.send_template(
                SendTemplateRequest(to="+595981123456", template_name="test_tpl")
            )
        assert exc_info.value.status_code == 401
        assert "Invalid OAuth access token" in exc_info.value.message


def test_otp_lifecycle_expiration_lockout_and_cooldown() -> None:
    mgr = OtpManager(default_expiry_seconds=120, code_length=6, max_attempts=3, cooldown_seconds=60)
    phone = "+595 981 555 777"

    code, record = mgr.create_otp(phone, purpose="sso_login")
    assert len(code) == 6
    assert code.isdigit()
    assert record.code_hash != code

    # Cooldown check
    with pytest.raises(ValueError, match="Rate limited"):
        mgr.create_otp(phone, purpose="sso_login")

    # Wrong attempt 1 & 2
    res1 = mgr.verify_otp(phone, "000000", purpose="sso_login")
    assert res1.success is False
    assert res1.status == OtpStatus.INVALID_CODE
    assert "2 attempt(s) remaining" in res1.message

    # Correct verification on attempt 2
    res_ok = mgr.verify_otp(phone, code, purpose="sso_login")
    assert res_ok.success is True
    assert res_ok.status == OtpStatus.VERIFIED
    assert res_ok.reference_id == record.reference_id

    # Replay protection
    res_replay = mgr.verify_otp(phone, code, purpose="sso_login")
    assert res_replay.success is False
    assert res_replay.status == OtpStatus.ALREADY_USED

    # Expiration test
    mgr.clear()
    code_exp, rec_exp = mgr.create_otp(phone, expiry_seconds=30)
    res_exp = mgr.verify_otp(
        phone, code_exp, now=rec_exp.created_at + timedelta(seconds=31)
    )
    assert res_exp.success is False
    assert res_exp.status == OtpStatus.EXPIRED

    # Max attempts lockout test
    mgr.clear()
    code_lock, _ = mgr.create_otp(phone)
    mgr.verify_otp(phone, "111111")
    mgr.verify_otp(phone, "222222")
    res_lock = mgr.verify_otp(phone, "333333")
    assert res_lock.status == OtpStatus.MAX_ATTEMPTS_EXCEEDED
    res_after_lock = mgr.verify_otp(phone, code_lock)
    assert res_after_lock.status == OtpStatus.MAX_ATTEMPTS_EXCEEDED


def test_webhook_challenge_and_hmac_signature() -> None:
    assert (
        verify_hub_challenge("subscribe", "sec_123", "998877", "sec_123") == "998877"
    )
    with pytest.raises(WebhookSecurityError):
        verify_hub_challenge("subscribe", "wrong", "998877", "sec_123")

    secret = "webhook_app_secret_key"
    raw = b'{"object":"whatsapp_business_account","entry":[]}'
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()

    assert verify_meta_signature(raw, f"sha256={sig}", secret) is True
    with pytest.raises(WebhookSecurityError):
        verify_meta_signature(raw, "sha256=bad", secret)
    with pytest.raises(WebhookSecurityError):
        verify_meta_signature(raw, None, secret)

    event_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "statuses": [
                                {
                                    "id": "wamid.999",
                                    "status": "delivered",
                                    "timestamp": "1728734450",
                                    "recipient_id": "595981445566",
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    ack = process_webhook_payload(event_payload)
    assert ack.success is True
    assert ack.processed_statuses == 1
    assert ack.statuses[0]["message_id"] == "wamid.999"
    assert ack.statuses[0]["status"] == "delivered"


def test_fastapi_otp_and_webhook_routes_end_to_end(test_settings: WhatsAppSettings) -> None:
    sent_codes: list[str] = []

    async def mock_meta_api(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        params = body["template"]["components"][0]["parameters"]
        sent_codes.append(params[0]["text"])
        return httpx.Response(
            200,
            json={
                "messaging_product": "whatsapp",
                "messages": [{"id": "wamid.otp_msg_001"}],
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_meta_api))
    wa_client = WhatsAppCloudApiClient(config=test_settings, http_client=http_client)
    isolated_otp = OtpManager(default_expiry_seconds=300, cooldown_seconds=60)

    app.dependency_overrides[get_whatsapp_client] = lambda: wa_client
    app.dependency_overrides[get_otp_manager] = lambda: isolated_otp

    try:
        with TestClient(app) as client:
            # 1. Send OTP via endpoint
            send_res = client.post(
                "/api/v1/otp/send",
                json={
                    "phone_number": "+595 981 222 333",
                    "purpose": "sso_login",
                    "meta": {"request_id": "req_1"},
                    "custom_data": {"user_id": "u_42"},
                },
            )
            assert send_res.status_code == 200
            send_json = send_res.json()
            assert send_json["success"] is True
            assert send_json["whatsapp_message_id"] == "wamid.otp_msg_001"
            assert "test_code" not in send_json
            assert send_json["meta"] == {"request_id": "req_1"}
            assert len(sent_codes) == 1

            # 2. Verify OTP via endpoint
            verify_res = client.post(
                "/api/v1/otp/verify",
                json={
                    "phone_number": "+595 981 222 333",
                    "code": sent_codes[0],
                    "purpose": "sso_login",
                    "meta": {"request_id": "req_2"},
                },
            )
            assert verify_res.status_code == 200
            verify_json = verify_res.json()
            assert verify_json["success"] is True
            assert verify_json["status"] == "verified"
            assert verify_json["meta"] == {"request_id": "req_2"}

            # 3. Webhook POST without signature must be rejected with 403
            wh_unauth = client.post("/api/v1/webhook", json={"object": "whatsapp_business_account", "entry": []})
            assert wh_unauth.status_code == 403

            # 4. Webhook POST with valid HMAC signature succeeds
            raw_wh = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode("utf-8")
            app_secret = settings.get_app_secret()
            sig = hmac.new(app_secret.encode("utf-8"), raw_wh, hashlib.sha256).hexdigest()
            wh_ok = client.post(
                "/api/v1/webhook",
                content=raw_wh,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": f"sha256={sig}",
                },
            )
            assert wh_ok.status_code == 200
            assert wh_ok.json()["success"] is True
    finally:
        app.dependency_overrides.clear()
