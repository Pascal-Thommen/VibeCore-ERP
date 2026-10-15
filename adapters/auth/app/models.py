"""
VibeCore ERP Auth Adapter Data Models and Schemas.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_id: str = Field(..., description="Unique user identifier mapped from Google sub")
    email: str = Field(..., description="Verified email address from Google")
    name: str | None = Field(None, description="Full display name")
    picture: str | None = Field(None, description="Avatar image URL")
    roles: list[str] = Field(default_factory=list, description="Assigned VibeCore roles")
    auth_provider: str = Field(default="google", description="Identity provider name")
    meta: dict[str, Any] | None = Field(default=None, description="Extensible metadata")
    custom_data: dict[str, Any] | None = Field(default=None, description="Extensible custom data")


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    access_token: str = Field(..., description="Signed VibeCore session JWT token")
    token_type: str = Field(default="Bearer", description="OAuth2 token type")
    expires_in: int = Field(default=3600, description="Token validity in seconds")
    user: UserInfo = Field(..., description="Authenticated user profile and roles")
    meta: dict[str, Any] | None = Field(default=None, description="Extensible metadata")
    custom_data: dict[str, Any] | None = Field(default=None, description="Extensible custom data")


class LoginInitiationResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    authorization_url: str = Field(
        ..., description="Full Google OAuth 2.0 authorization URL with PKCE"
    )
    state: str = Field(..., description="Cryptographic CSRF state parameter")
    meta: dict[str, Any] | None = Field(default=None, description="Extensible metadata")


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str = Field(default="healthy", description="Overall health state")
    service: str = Field(default="vibecore-auth-adapter", description="Service identifier")
    version: str = Field(default="0.1.0", description="Service version")
    google_oauth_configured: bool = Field(
        ..., description="Whether Google OAuth credentials are set"
    )
    timestamp: str = Field(..., description="ISO 8601 current timestamp")
    meta: dict[str, Any] | None = Field(default=None, description="Extensible metadata")


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str = Field(default="ready", description="Service readiness state")
    checks: dict[str, bool] = Field(..., description="Status of individual readiness checks")
    timestamp: str = Field(..., description="ISO 8601 current timestamp")


class LogoutResponse(BaseModel):
    status: str = Field(default="logged_out", description="Logout confirmation")
    message: str = Field(default="Erfolgreich abgemeldet.", description="Human readable message")


class ErrorResponse(BaseModel):
    error: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    detail: str | None = Field(None, description="Technical detail or context")
    trace_id: str | None = Field(None, description="Correlation Trace ID")
