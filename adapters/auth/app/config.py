"""
VibeCore ERP Auth Adapter Configuration.
Loads configuration from environment variables or .env files.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Google OAuth 2.0 & OIDC
    google_client_id: str = Field(
        default="mock-client-id.apps.googleusercontent.com",
        description="Google OAuth 2.0 Client ID",
    )
    google_client_secret: str = Field(
        default="mock-client-secret-key-12345",
        description="Google OAuth 2.0 Client Secret",
    )
    google_redirect_uri: str = Field(
        default="http://localhost:8001/auth/google/callback",
        description="Google OAuth 2.0 Authorized Redirect URI",
    )

    # Google Endpoints
    google_auth_url: str = Field(
        default="https://accounts.google.com/o/oauth2/v2/auth",
        description="Google Authorization Endpoint",
    )
    google_token_url: str = Field(
        default="https://oauth2.googleapis.com/token",
        description="Google Token Exchange Endpoint",
    )
    google_jwks_url: str = Field(
        default="https://www.googleapis.com/oauth2/v3/certs",
        description="Google Public JWKS Endpoint",
    )
    google_issuer_urls: list[str] = Field(
        default=["https://accounts.google.com", "accounts.google.com"],
        description="Valid Google ID Token Issuer URLs",
    )

    # VibeCore JWT & Session (ADR 0004)
    jwt_secret: str = Field(
        default="vibecore-super-secure-production-jwt-secret-min-32-chars-long",
        description="Secret key for signing VibeCore session JWT tokens",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT algorithm for VibeCore session tokens",
    )
    jwt_expiration_minutes: int = Field(
        default=60,
        description="VibeCore access token expiration in minutes (ADR 0004 specifies 1 hour)",
    )
    jwt_issuer: str = Field(
        default="vibecore-auth",
        description="VibeCore JWT Issuer claim (iss)",
    )
    jwt_audience: str = Field(
        default="vibeshell",
        description="VibeCore JWT Audience claim (aud)",
    )

    # State & Cookie Security
    cookie_secret: str = Field(
        default="vibecore-cookie-signing-secret-at-least-32-bytes-secure",
        description="Secret key for HMAC signing of OAuth state and PKCE cookies",
    )
    cookie_secure: bool = Field(
        default=False,
        description="Set to True in production to enforce HTTPS-only cookies",
    )
    cookie_same_site: str = Field(
        default="lax",
        description="SameSite cookie policy (lax or strict)",
    )
    cookie_state_name: str = Field(
        default="vibecore_oauth_state",
        description="Cookie name for temporary PKCE state",
    )
    cookie_session_name: str = Field(
        default="vibecore_session",
        description="Cookie name for VibeCore session token",
    )

    # Role Mapping & Access Control
    admin_emails: list[str] = Field(
        default=["pascal@vibecore.org", "pascalsolarluchs@gmail.com"],
        description="List of Google account emails granted ADMIN and ACCOUNTANT roles",
    )
    default_role: str = Field(
        default="USER",
        description="Default role assigned to verified Google users",
    )

    # Resilience & Timeouts (Säule 1)
    http_timeout_seconds: float = Field(
        default=10.0,
        description="Explicit HTTP network timeout in seconds for external Google API calls",
    )
    jwks_cache_ttl_seconds: int = Field(
        default=3600,
        description="Time-to-live for cached Google Public JWKS keys in seconds",
    )

    # CORS
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000", "http://localhost:8001"],
        description="Allowed CORS origins",
    )


settings = Settings()
