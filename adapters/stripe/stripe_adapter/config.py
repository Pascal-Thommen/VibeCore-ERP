"""
Configuration management for Stripe Payment Gateway Adapter.
Follows 12-factor principles using Pydantic Settings.
"""


from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Stripe API Credentials
    stripe_secret_key: str = Field(
        default="sk_test_mock_secret_key_12345",
        validation_alias="STRIPE_SECRET_KEY",
        description="Secret API key issued by Stripe dashboard",
    )
    stripe_publishable_key: str = Field(
        default="pk_test_mock_publishable_key_12345",
        validation_alias="STRIPE_PUBLISHABLE_KEY",
        description="Publishable API key for client-side Stripe integrations",
    )
    stripe_webhook_secret: str = Field(
        default="whsec_test_webhook_signing_secret_12345",
        validation_alias="STRIPE_WEBHOOK_SECRET",
        description="Secret key for cryptographically verifying Stripe webhook signatures",
    )
    stripe_default_currency: str = Field(
        default="USD",
        validation_alias="STRIPE_DEFAULT_CURRENCY",
        description="Default currency ISO code (e.g. USD, EUR, PYG)",
    )
    stripe_env: str = Field(
        default="sandbox",
        validation_alias="STRIPE_ENV",
        description="Execution environment: 'sandbox' or 'production'",
    )

    # API Base URL
    stripe_base_url: str | None = Field(
        default=None,
        validation_alias="STRIPE_BASE_URL",
        description="Custom base URL override for Stripe API (e.g. for testing)",
    )

    # Adapter Persistence
    database_url: str = Field(
        default="sqlite:///./stripe_transactions.db",
        validation_alias="DATABASE_URL",
        description="SQLAlchemy database connection string for local transaction store",
    )

    # Adapter Security & Networking
    adapter_api_key: str | None = Field(
        default=None,
        validation_alias="ADAPTER_API_KEY",
        description="Optional shared secret to secure internal adapter endpoints",
    )
    request_timeout_seconds: float = Field(
        default=10.0,
        validation_alias="REQUEST_TIMEOUT_SECONDS",
        description="Network request timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        validation_alias="MAX_RETRIES",
        description="Maximum retry attempts on transient network errors",
    )
    webhook_tolerance_seconds: int = Field(
        default=300,
        validation_alias="WEBHOOK_TOLERANCE_SECONDS",
        description="Allowed clock skew in seconds for webhook timestamp verification",
    )
    log_level: str = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
        description="Logging verbosity level",
    )

    @property
    def resolved_base_url(self) -> str:
        if self.stripe_base_url:
            return self.stripe_base_url.rstrip("/")
        return "https://api.stripe.com"


settings = Settings()
