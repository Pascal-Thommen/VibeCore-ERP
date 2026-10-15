"""Typed client for VibeCore Auth Adapter (Google OAuth 2.0 / OIDC SSO)."""

from __future__ import annotations

import httpx

from vibecore._base import BaseHttpClient
from vibecore.auth.models import (
    HealthResponse,
    LoginInitiationResponse,
    LogoutResponse,
    ReadinessResponse,
    TokenResponse,
    UserInfo,
)


class AuthClient(BaseHttpClient):
    """Client for VibeCore Google OAuth 2.0 and OIDC authentication microservice."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            transport=transport,
        )

    def health(self) -> HealthResponse:
        """Liveness check for Auth adapter."""
        resp = self._request("GET", "/health")
        self._raise_for_status(resp, adapter_type="auth")
        return HealthResponse.model_validate(resp.json())

    def ready(self) -> ReadinessResponse:
        """Readiness probe for Auth adapter."""
        resp = self._request("GET", "/ready")
        self._raise_for_status(resp, adapter_type="auth")
        return ReadinessResponse.model_validate(resp.json())

    def get_login_url(self, redirect_after_login: str | None = None) -> LoginInitiationResponse:
        """
        Initiate Google OAuth 2.0 PKCE login flow.
        Returns the authorization URL and cryptographic state token.
        """
        params = {}
        if redirect_after_login:
            params["redirect_after_login"] = redirect_after_login

        resp = self._request(
            "GET",
            "/auth/google/login",
            params=params,
            headers={"Accept": "application/json"},
        )
        self._raise_for_status(resp, adapter_type="auth")
        return LoginInitiationResponse.model_validate(resp.json())

    def exchange_code(
        self,
        code: str,
        state: str,
        cookie_state: str | None = None,
    ) -> TokenResponse:
        """
        Exchange Google authorization code and state token for a VibeCore session JWT.
        """
        headers = {}
        if cookie_state:
            headers["Cookie"] = f"vibecore_oauth_state={cookie_state}"

        resp = self._request(
            "GET",
            "/auth/google/callback",
            params={"code": code, "state": state},
            headers=headers if headers else None,
        )
        self._raise_for_status(resp, adapter_type="auth")
        return TokenResponse.model_validate(resp.json())

    def get_current_user(self, token: str) -> UserInfo:
        """
        Validate VibeCore session token (/auth/me) and return authenticated user profile.
        """
        clean_token = token.removeprefix("Bearer ").strip()
        resp = self._request(
            "GET",
            "/auth/me",
            headers={"Authorization": f"Bearer {clean_token}"},
        )
        self._raise_for_status(resp, adapter_type="auth")
        return UserInfo.model_validate(resp.json())

    def logout(self) -> LogoutResponse:
        """Terminate the current authentication session."""
        resp = self._request("POST", "/auth/logout")
        self._raise_for_status(resp, adapter_type="auth")
        return LogoutResponse.model_validate(resp.json())
