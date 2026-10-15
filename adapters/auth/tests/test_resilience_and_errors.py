"""
Tests for Resilience, Network Timeouts, CSRF attacks, and Error Handling (Säule 1 & Säule 3).
"""

from unittest.mock import AsyncMock

from app.config import settings
from app.google_client import (
    GoogleAuthException,
    GoogleAuthTimeoutException,
    GoogleOAuthClient,
)
from app.pkce import create_signed_state
from app.routers.auth import get_google_client


def test_user_cancelled_login(client):
    res = client.get(
        "/auth/google/callback?error=access_denied&error_description=The+user+cancelled+the+sign-in"
    )
    assert res.status_code == 400
    assert "cancelled or failed" in res.json()["message"]


def test_missing_code_or_state(client):
    res1 = client.get("/auth/google/callback")
    assert res1.status_code == 400
    assert "Missing 'code'" in res1.json()["message"]

    res2 = client.get("/auth/google/callback?code=some-code")
    assert res2.status_code == 400
    assert "Missing 'state'" in res2.json()["message"]


def test_csrf_cookie_mismatch(client):
    secret = settings.cookie_secret
    state_param = create_signed_state({"code_verifier": "v1"}, secret_key=secret)
    state_cookie = create_signed_state({"code_verifier": "v2"}, secret_key=secret)

    res = client.get(
        f"/auth/google/callback?code=some-code&state={state_param}",
        cookies={"vibecore_oauth_state": state_cookie},
    )
    assert res.status_code == 403
    assert "CSRF" in res.json()["message"]


def test_tampered_state(client):
    tampered_state = "invalid.signature"
    res = client.get(f"/auth/google/callback?code=some-code&state={tampered_state}")
    assert res.status_code == 403
    assert "CSRF" in res.json()["message"]


def test_google_token_exchange_timeout(client):
    secret = settings.cookie_secret
    state = create_signed_state({"code_verifier": "test_verifier"}, secret_key=secret)

    mock_client = GoogleOAuthClient(app_settings=settings)
    mock_client.exchange_code_for_tokens = AsyncMock(
        side_effect=GoogleAuthTimeoutException("Google token exchange timed out")
    )
    client.app.dependency_overrides[get_google_client] = lambda: mock_client

    try:
        res = client.get(f"/auth/google/callback?code=some-code&state={state}")
        assert res.status_code == 504
        msg = res.json()["message"].lower()
        assert "timeout" in msg or "timed out" in msg
    finally:
        client.app.dependency_overrides.clear()


def test_google_jwks_timeout(client):
    secret = settings.cookie_secret
    state = create_signed_state({"code_verifier": "test_verifier"}, secret_key=secret)

    mock_client = GoogleOAuthClient(app_settings=settings)
    mock_client.exchange_code_for_tokens = AsyncMock(return_value={"id_token": "some.token.value"})
    mock_client.validate_id_token = AsyncMock(
        side_effect=GoogleAuthTimeoutException("Google JWKS timed out")
    )
    client.app.dependency_overrides[get_google_client] = lambda: mock_client

    try:
        res = client.get(f"/auth/google/callback?code=some-code&state={state}")
        assert res.status_code == 504
        msg = res.json()["message"].lower()
        assert "timeout" in msg or "timed out" in msg
    finally:
        client.app.dependency_overrides.clear()


def test_google_exchange_invalid_grant(client):
    secret = settings.cookie_secret
    state = create_signed_state({"code_verifier": "test_verifier"}, secret_key=secret)

    mock_client = GoogleOAuthClient(app_settings=settings)
    mock_client.exchange_code_for_tokens = AsyncMock(
        side_effect=GoogleAuthException(
            "Google token exchange failed: invalid_grant", status_code=400
        )
    )
    client.app.dependency_overrides[get_google_client] = lambda: mock_client

    try:
        res = client.get(f"/auth/google/callback?code=bad-code&state={state}")
        assert res.status_code == 400
        assert "invalid_grant" in res.json()["message"]
    finally:
        client.app.dependency_overrides.clear()


def test_trace_id_propagation(client):
    custom_trace_id = "trace_custom_xyz_987"
    res = client.get("/health", headers={"X-Trace-Id": custom_trace_id})
    assert res.status_code == 200
    assert res.headers.get("X-Trace-Id") == custom_trace_id
