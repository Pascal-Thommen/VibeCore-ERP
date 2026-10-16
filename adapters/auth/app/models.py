"""
VibeCore ERP Auth Adapter Data Models and Schemas.
Includes RFC 7517 JWKS, TokenResponse with Refresh Token, and Tenant ID.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_id: str = Field(..., description="Unique user identifier mapped from Google sub")
    email: str = Field(..., description="Verified email address from Google")
    tenant_id: str = Field(..., description="Assigned multi-tenant identifier")
    name: str | None = Field(None, description="Full display name")
    picture: str | None = Field(None, description="Avatar image URL")
    roles: list[str] = Field(default_factory=list, description="Assigned VibeCore roles")
    auth_provider: str = Field(default="google", description="Identity provider name")
    meta: dict[str, Any] | None = Field(default=None, description="Extensible metadata")
    custom_data: dict[str, Any] | None = Field(default=None, description="Extensible custom data")


class TokenResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    access_token: str = Field(..., description="Signed VibeCore session JWT access token (RS256)")
    refresh_token: str | None = Field(
        None, description="Signed VibeCore refresh token (7 days validity)"
    )
    token_type: str = Field(default="Bearer", description="OAuth2 token type")
    expires_in: int = Field(default=3600, description="Access token validity in seconds")
    refresh_expires_in: int | None = Field(
        default=604800, description="Refresh token validity in seconds (7 days)"
    )
    tenant_id: str = Field(..., description="Assigned multi-tenant identifier")
    user: UserInfo = Field(..., description="Authenticated user profile and roles")
    meta: dict[str, Any] | None = Field(default=None, description="Extensible metadata")
    custom_data: dict[str, Any] | None = Field(default=None, description="Extensible custom data")


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    refresh_token: str | None = Field(
        default=None, description="VibeCore issued refresh token"
    )
    tenant_hint: str | None = Field(
        None, description="Optional tenant hint override or validation"
    )


class LoginInitiationResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    authorization_url: str = Field(
        ..., description="Full Google OAuth 2.0 authorization URL with PKCE"
    )
    state: str = Field(..., description="Cryptographic CSRF state parameter")
    meta: dict[str, Any] | None = Field(default=None, description="Extensible metadata")


class JWKSResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    keys: list[dict[str, Any]] = Field(
        ..., description="List of RFC 7517 compliant JSON Web Keys"
    )


class OpenIDConfigurationResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    issuer: str = Field(..., description="OIDC Issuer URL")
    authorization_endpoint: str = Field(..., description="OAuth 2.0 authorization endpoint")
    token_endpoint: str = Field(..., description="OAuth 2.0 token endpoint")
    jwks_uri: str = Field(..., description="Public JWKS URL")
    userinfo_endpoint: str = Field(..., description="OIDC userinfo endpoint")
    response_types_supported: list[str] = Field(default=["code"])
    subject_types_supported: list[str] = Field(default=["public"])
    id_token_signing_alg_values_supported: list[str] = Field(default=["RS256", "EdDSA"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str = Field(default="healthy", description="Overall health state")
    service: str = Field(default="vibecore-auth", description="Service identifier")
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
