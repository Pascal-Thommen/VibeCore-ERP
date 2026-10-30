"""Configuration for the VibeCore WhatsApp Cloud API Adapter."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class WhatsAppSettings(BaseSettings):
    """WhatsApp adapter runtime settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="WHATSAPP_",
    )

    # Meta WhatsApp Cloud API credentials
    meta_api_base_url: str = Field(
        default="https://graph.facebook.com",
        description="Meta Graph API base URL",
    )
    meta_api_version: str = Field(
        default="v21.0",
        description="Meta Graph API version",
    )
    meta_phone_number_id: str = Field(
        default="106540352242522",
        description="WhatsApp Business Phone Number ID",
    )
    meta_access_token: SecretStr | None = Field(
        default=SecretStr("vibecore-whatsapp-dev-access-token"),
        description="Meta System User Access Token",
    )
    meta_access_token_file: Path | None = None

    meta_app_secret: SecretStr | None = Field(
        default=SecretStr("vibecore-whatsapp-webhook-app-secret-32b"),
        description="Meta App Secret for X-Hub-Signature-256 HMAC verification",
    )
    meta_app_secret_file: Path | None = None

    meta_webhook_verify_token: SecretStr = Field(
        default=SecretStr("vibecore_meta_verify_secret"),
        description="Verification token for Meta Webhook Hub Challenge",
    )
    meta_webhook_verify_token_file: Path | None = None

    # OTP settings
    otp_default_expiry_seconds: int = 300
    otp_code_length: int = 6
    otp_max_attempts: int = 3
    otp_cooldown_seconds: int = 60
    otp_template_name: str = "vibecore_auth_otp"
    otp_template_language: str = "es"

    # Resilience & Timeouts (Säule 1)
    http_timeout_seconds: float = 10.0

    def get_access_token(self) -> str:
        """Resolve Meta Graph API access token from secret file or environment."""
        if self.meta_access_token_file is not None and self.meta_access_token_file.is_file():
            return self.meta_access_token_file.read_text(encoding="utf-8").strip()
        if self.meta_access_token is not None:
            return self.meta_access_token.get_secret_value().strip()
        return ""

    def get_app_secret(self) -> str:
        """Resolve Meta app secret for HMAC webhook verification."""
        if self.meta_app_secret_file is not None and self.meta_app_secret_file.is_file():
            return self.meta_app_secret_file.read_text(encoding="utf-8").strip()
        if self.meta_app_secret is not None:
            return self.meta_app_secret.get_secret_value().strip()
        return ""

    def get_webhook_verify_token(self) -> str:
        """Resolve webhook verify token for Hub Challenge validation."""
        if (
            self.meta_webhook_verify_token_file is not None
            and self.meta_webhook_verify_token_file.is_file()
        ):
            return self.meta_webhook_verify_token_file.read_text(encoding="utf-8").strip()
        if self.meta_webhook_verify_token is not None:
            return self.meta_webhook_verify_token.get_secret_value().strip()
        return ""


settings = WhatsAppSettings()
