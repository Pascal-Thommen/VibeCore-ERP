"""Pydantic schemas and data models for VibeCore Auth Adapter."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserInfo(BaseModel):
    """Authenticated user profile and roles mapped from Google OIDC."""

    model_config = ConfigDict(extra="allow")

    user_id: str = Field(description="Unique user identifier mapped from Google sub")
    email: str = Field(description="Verified email address from Google")
    name: str | None = Field(default=None, description="Full display name")
    picture: str | None = Field(default=None, description="Avatar image URL")
    roles: list[str] = Field(default_factory=list, description="Assigned VibeCore roles")
    auth_provider: str = Field(default="google", description="Identity provider name")
    meta: dict[str, Any] | None = Field(default=None, description="Extensible metadata")
    custom_data: dict[str, Any] | None = Field(default=None, description="Extensible custom data")


class TokenResponse(BaseModel):
    """Session JWT token issued by VibeCore Auth Adapter."""

    model_config = ConfigDict(extra="allow")

    access_token: str = Field(description="Signed VibeCore session JWT token")
    token_type: str = Field(default="Bearer", description="OAuth2 token type")
    expires_in: int = Field(default=3600, description="Token validity in seconds")
    user: UserInfo = Field(description="Authenticated user profile and roles")
    meta: dict[str, Any] | None = Field(default=None, description="Extensible metadata")
    custom_data: dict[str, Any] | None = Field(default=None, description="Extensible custom data")


class LoginInitiationResponse(BaseModel):
    """Google OAuth 2.0 PKCE login initiation payload."""

    model_config = ConfigDict(extra="allow")

    authorization_url: str = Field(description="Full Google OAuth 2.0 authorization URL with PKCE")
    state: str = Field(description="Cryptographic CSRF state parameter")
    meta: dict[str, Any] | None = Field(default=None, description="Extensible metadata")


class HealthResponse(BaseModel):
    """Health check response for Auth Adapter."""

    model_config = ConfigDict(extra="allow")

    status: str = Field(default="healthy", description="Overall health state")
    service: str = Field(default="vibecore-auth-adapter", description="Service identifier")
    version: str = Field(default="0.1.0", description="Service version")
    google_oauth_configured: bool = Field(
        default=False, description="Whether Google OAuth credentials are set"
    )
    timestamp: str | None = Field(default=None, description="ISO 8601 current timestamp")
    meta: dict[str, Any] | None = Field(default=None, description="Extensible metadata")


class ReadinessResponse(BaseModel):
    """Readiness probe response for Auth Adapter."""

    model_config = ConfigDict(extra="allow")

    status: str = Field(default="ready", description="Service readiness state")
    checks: dict[str, bool] = Field(
        default_factory=dict, description="Status of individual readiness checks"
    )
    timestamp: str | None = Field(default=None, description="ISO 8601 current timestamp")


class LogoutResponse(BaseModel):
    """Logout confirmation response."""

    model_config = ConfigDict(extra="allow")

    status: str = Field(default="logged_out", description="Logout confirmation")
    message: str = Field(default="Erfolgreich abgemeldet.", description="Human readable message")
