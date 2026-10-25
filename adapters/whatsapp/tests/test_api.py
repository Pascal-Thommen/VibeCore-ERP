"""End-to-end endpoint tests for the WhatsApp Cloud API adapter FastAPI app."""

import hashlib
import hmac
import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.otp import otp_manager
from app.service_window import service_window_manager

client = TestClient(app)


def test_health_and_ready_endpoints() -> None:
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["adapter"] == "whatsapp-cloud-api"

    res_ready = client.get("/api/v1/ready")
    assert res_ready.status_code == 200
    assert res_ready.json()["status"] == "ready"


def test_meta_webhook_get_verification_flow() -> None:
    verify_token = settings.get_webhook_verify_token()

    # Valid challenge
    res = client.get(
        "/api/v1/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": verify_token,
            "hub.challenge": "987654321",
        },
    )
    assert res.status_code == 200
    assert res.text == "987654321"

    # Invalid token -> 403 Forbidden
    res_bad = client.get(
        "/api/v1/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "987654321",
        },
    )
    assert res_bad.status_code == 403


def test_meta_webhook_post_flow() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": "595981776655",
                                    "id": "wamid.123",
                                    "timestamp": str(int(datetime.now(UTC).timestamp())),
                                    "text": {"body": "Test msg"},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    raw_body = json.dumps(payload).encode()
    app_secret = settings.get_app_secret()
    headers = {"Content-Type": "application/json"}
    if app_secret:
        sig = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = f"sha256={sig}"

    res = client.post("/api/v1/webhook", content=raw_body, headers=headers)
    assert res.status_code == 200
    ack = res.json()
    assert ack["success"]
    assert ack["processed_messages"] == 1

    # Verify 24h window opened
    res_window = client.get("/api/v1/service-window/595981776655")
    assert res_window.status_code == 200
    assert res_window.json()["is_active"]


def test_send_template_endpoint() -> None:
    req = {
        "to": "+15550254555",
        "template_name": "otp_verification",
        "language_code": "es",
        "body_parameters": ["482910"],
        "button_parameters": ["482910"],
        "meta": {"trace_id": "test_trace_123"},
    }
    res = client.post("/api/v1/messages/send-template", json=req)
    assert res.status_code == 200
    data = res.json()
    assert data["success"]
    assert data["recipient"] == "15550254555"
    assert data["message_id"] is not None


def test_send_text_endpoint_window_control() -> None:
    phone = "595981223344"
    service_window_manager.clear(phone)

    req = {
        "to": phone,
        "message": "Hola, su pedido esta en camino",
        "enforce_24h_window": True,
    }

    # Window closed -> 400 Bad Request
    res_blocked = client.post("/api/v1/messages/send-text", json=req)
    assert res_blocked.status_code == 400
    assert "24-hour customer service window is closed" in res_blocked.json()["detail"]

    # Open window
    service_window_manager.record_incoming_message(phone)

    # Window open -> 200 OK
    res_ok = client.post("/api/v1/messages/send-text", json=req)
    assert res_ok.status_code == 200
    assert res_ok.json()["success"]


def test_otp_send_and_verify_cycle() -> None:
    otp_manager.clear()
    phone = "+595981001122"

    # 1. Send OTP
    send_req = {
        "phone_number": phone,
        "purpose": "sso_login",
        "expiry_seconds": 300,
        "send_via_whatsapp": True,
    }
    res_send = client.post("/api/v1/otp/send", json=send_req)
    assert res_send.status_code == 200
    send_data = res_send.json()
    assert send_data["success"]
    assert send_data["phone_number"] == "595981001122"
    otp_code = send_data["test_code"]
    assert otp_code is not None

    # 2. Verify with wrong code -> failure
    verify_bad = {
        "phone_number": phone,
        "code": "000000",
        "purpose": "sso_login",
    }
    res_verify_bad = client.post("/api/v1/otp/verify", json=verify_bad)
    assert res_verify_bad.status_code == 200
    assert not res_verify_bad.json()["success"]
    assert res_verify_bad.json()["status"] == "invalid_code"

    # 3. Verify with correct code -> success
    verify_good = {
        "phone_number": phone,
        "code": otp_code,
        "purpose": "sso_login",
    }
    res_verify_good = client.post("/api/v1/otp/verify", json=verify_good)
    assert res_verify_good.status_code == 200
    good_data = res_verify_good.json()
    assert good_data["success"]
    assert good_data["status"] == "verified"
    assert good_data["verified_at"] is not None

    # 4. Replay attack -> already used
    res_replay = client.post("/api/v1/otp/verify", json=verify_good)
    assert res_replay.status_code == 200
    assert not res_replay.json()["success"]
    assert res_replay.json()["status"] == "already_used"
