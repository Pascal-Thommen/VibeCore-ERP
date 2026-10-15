"""Unit and contract tests for AuthClient (Google OAuth 2.0 / OIDC SSO)."""

import httpx
import pytest

from vibecore.auth.client import AuthClient
from vibecore.auth.models import (
    HealthResponse,
    LoginInitiationResponse,
    LogoutResponse,
    ReadinessResponse,
    TokenResponse,
    UserInfo,
)
from vibecore.exceptions import AuthenticationError, TimeoutError


def test_auth_client_health():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "status": "healthy",
                "service": "vibecore-auth-adapter",
                "version": "0.1.0",
                "google_oauth_configured": True,
                "timestamp": "2026-10-15T22:00:00Z",
            },
        )

    client = AuthClient("http://auth.test", transport=httpx.MockTransport(handler))
    health = client.health()
    assert isinstance(health, HealthResponse)
    assert health.status == "healthy"
    assert health.google_oauth_configured is True
    client.close()


def test_auth_client_ready():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ready"
        return httpx.Response(
            200,
            json={
                "status": "ready",
                "checks": {"google_jwks": True, "session_signer": True},
                "timestamp": "2026-10-15T22:00:00Z",
            },
        )

    with AuthClient("http://auth.test", transport=httpx.MockTransport(handler)) as client:
        ready = client.ready()
        assert isinstance(ready, ReadinessResponse)
        assert ready.status == "ready"
        assert ready.checks["google_jwks"] is True


def test_auth_client_get_login_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/google/login"
        assert request.headers.get("accept") == "application/json"
        assert "redirect_after_login=https%3A%2F%2Fapp.vibecore.io" in str(request.url)
        return httpx.Response(
            200,
            json={
                "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=123",
                "state": "mock_signed_state_token",
            },
        )

    with AuthClient("http://auth.test", transport=httpx.MockTransport(handler)) as client:
        init = client.get_login_url(redirect_after_login="https://app.vibecore.io")
        assert isinstance(init, LoginInitiationResponse)
        assert init.authorization_url.startswith("https://accounts.google.com")
        assert init.state == "mock_signed_state_token"


def test_auth_client_exchange_code():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/google/callback"
        assert "code=auth_code_123" in str(request.url)
        assert "state=mock_signed_state_token" in str(request.url)
        assert "cookie" in request.headers
        return httpx.Response(
            200,
            json={
                "access_token": "jwt_session_token_xyz",
                "token_type": "Bearer",
                "expires_in": 3600,
                "user": {
                    "user_id": "google_sub_1001",
                    "email": "pascal@vibecore.io",
                    "name": "Pascal Thommen",
                    "picture": "https://lh3.googleusercontent.com/avatar",
                    "roles": ["admin", "finance_auditor"],
                    "auth_provider": "google",
                },
            },
        )

    with AuthClient("http://auth.test", transport=httpx.MockTransport(handler)) as client:
        token = client.exchange_code(
            code="auth_code_123",
            state="mock_signed_state_token",
            cookie_state="mock_signed_state_token",
        )
        assert isinstance(token, TokenResponse)
        assert token.access_token == "jwt_session_token_xyz"
        assert isinstance(token.user, UserInfo)
        assert token.user.email == "pascal@vibecore.io"
        assert "admin" in token.user.roles


def test_auth_client_get_current_user():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/me"
        assert request.headers.get("authorization") == "Bearer session_jwt_abc"
        return httpx.Response(
            200,
            json={
                "user_id": "google_sub_1001",
                "email": "pascal@vibecore.io",
                "name": "Pascal Thommen",
                "picture": None,
                "roles": ["developer"],
                "auth_provider": "google",
            },
        )

    with AuthClient("http://auth.test", transport=httpx.MockTransport(handler)) as client:
        user = client.get_current_user("session_jwt_abc")
        assert isinstance(user, UserInfo)
        assert user.user_id == "google_sub_1001"
        assert user.email == "pascal@vibecore.io"
        assert user.roles == ["developer"]


def test_auth_client_unauthorized_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"detail": "Authentication required. Provide Bearer token or session cookie."},
        )

    with AuthClient("http://auth.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AuthenticationError) as exc_info:
            client.get_current_user("invalid_token")
        assert exc_info.value.status_code == 401
        assert "Authentication required" in str(exc_info.value)


def test_auth_client_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            504,
            json={"detail": "Google OAuth endpoint timeout after 10s."},
        )

    with AuthClient("http://auth.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TimeoutError) as exc_info:
            client.exchange_code("code", "state")
        assert exc_info.value.status_code == 504
        assert "timeout" in str(exc_info.value).lower()


def test_auth_client_logout():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/logout"
        assert request.method == "POST"
        return httpx.Response(
            200,
            json={"status": "logged_out", "message": "Erfolgreich abgemeldet."},
        )

    with AuthClient("http://auth.test", transport=httpx.MockTransport(handler)) as client:
        resp = client.logout()
        assert isinstance(resp, LogoutResponse)
        assert resp.status == "logged_out"
