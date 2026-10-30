"""
Configuration management for SIFEN Fiscal Adapter.
Follows 12-factor principles using Pydantic Settings without redundant configuration ballast.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    sifen_env: str = Field(
        default="sandbox",
        validation_alias="SIFEN_ENV",
        description="Execution environment: 'sandbox' or 'production'",
    )
    sifen_base_url: str | None = Field(
        default=None,
        validation_alias="SIFEN_BASE_URL",
        description="Optional override base URL for SIFEN SOAP webservice",
    )
    database_url: str = Field(
        default="sqlite:///./sifen_outbox.db",
        validation_alias="DATABASE_URL",
        description="SQLAlchemy database connection string for local persistent DTE outbox queue",
    )
    adapter_api_key: str | None = Field(
        default=None,
        validation_alias="ADAPTER_API_KEY",
        description="Optional shared secret to secure internal adapter endpoints",
    )
    request_timeout_seconds: float = Field(
        default=10.0,
        validation_alias="REQUEST_TIMEOUT_SECONDS",
        description="Network request timeout in seconds for SIFEN SOAP transmission",
    )
    max_retries: int = Field(
        default=3,
        validation_alias="MAX_RETRIES",
        description="Maximum retry attempts per transmission on transient network errors",
    )
    log_level: str = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
        description="Logging verbosity level",
    )

    @property
    def resolved_base_url(self) -> str:
        if self.sifen_base_url:
            return self.sifen_base_url.rstrip("/")
        if self.sifen_env.lower() == "production":
            return "https://sifen.set.gov.py"
        return "https://sifen-test.set.gov.py"


settings = Settings()
