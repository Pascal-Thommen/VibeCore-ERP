"""
Configuration management for Pagopar Payment Gateway Adapter.
Follows 12-factor principles using Pydantic Settings.
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Pagopar Credentials
    pagopar_public_key: str = Field(
        default="test_public_key",
        validation_alias="PAGOPAR_PUBLIC_KEY",
        description="Public Key issued by Pagopar merchant dashboard",
    )
    pagopar_private_key: str = Field(
        default="test_private_key",
        validation_alias="PAGOPAR_PRIVATE_KEY",
        description="Private Key issued by Pagopar for cryptographic signing",
    )
    pagopar_env: str = Field(
        default="sandbox",
        validation_alias="PAGOPAR_ENV",
        description="Gateway execution environment: 'sandbox' or 'production'",
    )

    # API Base URLs
    pagopar_base_url: Optional[str] = Field(
        default=None,
        validation_alias="PAGOPAR_BASE_URL",
        description="Override base URL for Pagopar API v2",
    )
    pagopar_checkout_base_url: Optional[str] = Field(
        default=None,
        validation_alias="PAGOPAR_CHECKOUT_BASE_URL",
        description="Override base URL for Pagopar redirect checkout",
    )

    # Adapter Persistence
    database_url: str = Field(
        default="sqlite:///./pagopar_transactions.db",
        validation_alias="DATABASE_URL",
        description="SQLAlchemy database connection string for local transaction log",
    )

    # Adapter Security & Networking
    adapter_api_key: Optional[str] = Field(
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
    log_level: str = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
        description="Logging verbosity level",
    )

    @property
    def resolved_base_url(self) -> str:
        if self.pagopar_base_url:
            return self.pagopar_base_url.rstrip("/")
        if self.pagopar_env.lower() == "production":
            return "https://api.pagopar.com"
        return "https://api-sandbox.pagopar.com"

    @property
    def resolved_checkout_base_url(self) -> str:
        if self.pagopar_checkout_base_url:
            return self.pagopar_checkout_base_url.rstrip("/")
        if self.pagopar_env.lower() == "production":
            return "https://www.pagopar.com/pagos"
        return "https://sandbox.pagopar.com/pagos"


settings = Settings()
