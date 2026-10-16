"""Configuration settings for Bancard vPOS Adapter Microservice."""

import os
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field

from app.bancard.constants import BancardEnvironment


class Settings(BaseSettings):
    bancard_environment: BancardEnvironment = Field(
        default=BancardEnvironment.STAGING,
        validation_alias="BANCARD_ENVIRONMENT",
    )
    bancard_public_key: str = Field(
        default="test_public_key",
        validation_alias="BANCARD_PUBLIC_KEY",
    )
    bancard_private_key: str = Field(
        default="test_private_key",
        validation_alias="BANCARD_PRIVATE_KEY",
    )
    bancard_staging_url: str = Field(
        default="https://vpos.infonet.com.py:8888",
        validation_alias="BANCARD_STAGING_URL",
    )
    bancard_prod_url: str = Field(
        default="https://vpos.infonet.com.py",
        validation_alias="BANCARD_PROD_URL",
    )
    database_url: str = Field(
        default="sqlite:///./bancard_pay.db",
        validation_alias="DATABASE_URL",
    )
    vibecore_webhook_secret: str = Field(
        default="vibecore_pay_webhook_secret_key_2026",
        validation_alias="VIBECORE_WEBHOOK_SECRET",
    )
    downstream_webhook_urls: List[str] = Field(
        default_factory=lambda: ["http://localhost:8000/api/v1/payments/webhook/bancard"],
        validation_alias="DOWNSTREAM_WEBHOOK_URLS",
    )
    request_timeout_seconds: float = Field(
        default=10.0,
        validation_alias="REQUEST_TIMEOUT_SECONDS",
    )
    max_webhook_retries: int = Field(
        default=3,
        validation_alias="MAX_WEBHOOK_RETRIES",
    )
    qr_expiration_minutes: int = Field(
        default=15,
        validation_alias="QR_EXPIRATION_MINUTES",
    )
    service_name: str = "vibecore-pay-bancard"
    service_version: str = "1.0.0"

    @property
    def bancard_base_url(self) -> str:
        if self.bancard_environment == BancardEnvironment.PRODUCTION:
            return self.bancard_prod_url.rstrip("/")
        return self.bancard_staging_url.rstrip("/")


settings = Settings()
