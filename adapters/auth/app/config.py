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

    # VibeCore JWT & Cryptographic Token Management (ADR 0004 & RS256/EdDSA IdP)
    jwt_secret: str = Field(
        default="vibecore-super-secure-production-jwt-secret-min-32-chars-long",
        description="Secret key for signing legacy or fallback HMAC session tokens",
    )
    jwt_algorithm: str = Field(
        default="RS256",
        description="Asymmetric algorithm for VibeCore session tokens (RS256 or EdDSA)",
    )
    jwt_key_id: str = Field(
        default="vibecore-auth-key-1",
        description="Key identifier (kid) published in JWKS and JWT header",
    )
    jwt_private_key_pem: str | None = Field(
        default=None,
        description="Optional PEM string for RSA/Ed25519 private key. If omitted, auto-generated.",
    )
    jwt_private_key_path: str | None = Field(
        default=None,
        description="Optional file path to PEM-encoded RSA/Ed25519 private key",
    )
    jwt_expiration_minutes: int = Field(
        default=60,
        description="VibeCore access token expiration in minutes (ADR 0004 specifies 1 hour)",
    )
    jwt_refresh_expiration_days: int = Field(
        default=7,
        description="VibeCore refresh token expiration in days (ADR 0004 specifies 7 days)",
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

    # Mandanten-Zuordnung (Tenant Resolution)
    tenant_domain_mapping: dict[str, str] = Field(
        default_factory=lambda: {
            "vibecore.org": "tenant_vibecore",
            "vibecore.py": "tenant_vibecore",
            "solarluchs.de": "tenant_solarluchs",
        },
        description="Domain to tenant ID mapping dictionary",
    )
    tenant_organization_mapping: dict[str, str] = Field(
        default_factory=lambda: {
            "pascalsolarluchs@gmail.com": "tenant_vibecore",
            "pascal@vibecore.org": "tenant_vibecore",
        },
        description="Specific user email to tenant ID mapping dictionary",
    )
    default_tenant_id: str = Field(
        default="tenant_default",
        description="Default fallback tenant ID",
    )
    public_tenant_prefix: str = Field(
        default="tenant_user_",
        description="Prefix for personal tenants of public email domain users (gmail, yahoo, etc.)",
    )

    # Resilience & Timeouts (Säule 1)
    http_timeout_seconds: float = Field(
        default=10.0,
        description="Explicit HTTP network timeout in seconds for external Google API calls",
    )
    http_max_retries: int = Field(
        default=3,
        description="Maximum number of retries against external identity provider endpoints",
    )
    http_retry_delay_seconds: float = Field(
        default=0.2,
        description="Initial delay in seconds for exponential backoff retry",
    )
    http_retry_backoff_factor: float = Field(
        default=2.0,
        description="Backoff multiplier for consecutive retries",
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
