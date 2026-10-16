"""
Additional edge-case tests to achieve near 100% test coverage across all modules.
"""

from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
import httpx
import pytest

from app.config import settings
from app.google_client import GoogleAuthException, GoogleOAuthClient
from app.main import app
from app.models import UserInfo
from app.routers.auth import get_google_client
from app.session import SessionException, session_manager


def test_google_callback_missing_id_token(client):
    secret = settings.cookie_secret
    from app.pkce import create_signed_state

    state = create_signed_state({"code_verifier": "v123"}, secret_key=secret)
    mock_client = GoogleOAuthClient(app_settings=settings)
    # Returns tokens without id_token
    mock_client.exchange_code_for_tokens = AsyncMock(return_value={"access_token": "acc_123"})
    client.app.dependency_overrides[get_google_client] = lambda: mock_client

    try:
        res = client.get(f"/auth/google/callback?code=some-code&state={state}")
        assert res.status_code == 502
        assert "id_token" in res.json()["message"]
    finally:
        client.app.dependency_overrides.clear()


def test_generic_exception_handler():
    no_raise_client = TestClient(app, raise_server_exceptions=False)
    mock_client = GoogleOAuthClient(app_settings=settings)
    mock_client.exchange_code_for_tokens = AsyncMock(side_effect=RuntimeError("Unexpected crash"))
    from app.pkce import create_signed_state

    state = create_signed_state({"code_verifier": "v123"}, secret_key=settings.cookie_secret)
    app.dependency_overrides[get_google_client] = lambda: mock_client

    try:
        res = no_raise_client.get(f"/auth/google/callback?code=some-code&state={state}")
        assert res.status_code == 500
        assert res.json()["error"] == "internal_error"
    finally:
        app.dependency_overrides.clear()


def test_session_manager_verify_wrong_token_use():
    user = UserInfo(user_id="u1", email="u1@vibecore.org", tenant_id="tenant_vibecore", roles=["USER"])
    tokens = session_manager.issue_token_pair(user)

    # Passing refresh token to verify_session_token (expects access token)
    with pytest.raises(SessionException, match="Expected access token"):
        session_manager.verify_session_token(tokens.refresh_token)


def test_session_manager_refresh_without_tenant_in_payload():
    # Construct a refresh token payload without tenant_id to hit fallback
    import time
    now = int(time.time())
    payload = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": "user_notenant",
        "email": "notenant@vibecore.org",
        "roles": ["USER"],
        "token_use": "refresh",
        "jti": "jti_123",
        "iat": now,
        "exp": now + 3600,
    }
    tok = session_manager.crypto.sign(payload)
    refreshed = session_manager.refresh_session(tok)
    assert refreshed.tenant_id == "tenant_vibecore"


def test_auth_verify_endpoint_invalid_token(client):
    res = client.post("/auth/verify?token=invalid.token.value")
    assert res.status_code in [400, 401]


@pytest.mark.asyncio
async def test_google_client_id_token_unverified_email(rsa_keypair, make_google_id_token, test_settings):
    # Make ID token with email_verified = False and matching audience
    id_token = make_google_id_token(
        email="unverified@vibecore.org",
        aud=test_settings.google_client_id,
        email_verified=False,
    )
    client = GoogleOAuthClient(app_settings=test_settings)
    client._jwks_cache = rsa_keypair["jwks"]
    client._jwks_cached_at = 9999999999.0

    with pytest.raises(GoogleAuthException, match="not verified"):
        await client.validate_id_token(id_token)


@pytest.mark.asyncio
async def test_google_client_jwks_network_error():
    settings_fast_retry = settings.model_copy(update={"http_max_retries": 1, "http_retry_delay_seconds": 0.01})
    client = GoogleOAuthClient(app_settings=settings_fast_retry)

    async def mock_get(url):
        raise httpx.ConnectError("Network is down")

    mock_http = MagicMock()
    mock_http.is_closed = False
    mock_http.get = mock_get
    client._http_client = mock_http

    with pytest.raises(GoogleAuthException, match="Network error while contacting Google OAuth servers"):
        await client.get_google_jwks(force_refresh=True)


def test_readyz_crypto_failure(client, monkeypatch):
    from app import crypto
    monkeypatch.setattr(crypto.crypto_manager, "get_jwks", MagicMock(side_effect=Exception("Crypto down")))

    res = client.get("/readyz")
    assert res.status_code == 200
    assert res.json()["status"] == "not_ready"
    assert res.json()["checks"]["asymmetric_crypto_keys"] is False
