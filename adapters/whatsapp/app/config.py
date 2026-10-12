"""Configuration for the WhatsApp Cloud API Adapter."""

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

    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"

    # Meta WhatsApp Cloud API credentials
    meta_api_base_url: str = "https://graph.facebook.com"
    meta_api_version: str = "v21.0"
    meta_phone_number_id: str = "106540352242522"
    meta_business_account_id: str | None = None

    meta_access_token: SecretStr | None = None
    meta_access_token_file: Path | None = None

    meta_app_secret: SecretStr | None = None
    meta_app_secret_file: Path | None = None

    meta_webhook_verify_token: SecretStr = Field(
        default_factory=lambda: SecretStr("vibecore_meta_verify_secret")
    )
    meta_webhook_verify_token_file: Path | None = None

    # OTP settings
    otp_default_expiry_seconds: int = 300
    otp_code_length: int = 6
    otp_max_attempts: int = 3
    otp_cooldown_seconds: int = 60
    otp_template_name: str = "vibecore_auth_otp"
    otp_template_language: str = "es"

    # Testing & Sandboxing
    meta_test_mode: bool = True
    meta_test_phone_numbers: list[str] = [
        "+15550254555",
        "+15550254556",
        "+15551234567",
    ]

    def get_access_token(self) -> str:
        """Resolve Meta Graph API access token from environment or secret file."""
        if self.meta_access_token is not None:
            return self.meta_access_token.get_secret_value()
        if self.meta_access_token_file is not None and self.meta_access_token_file.is_file():
            return self.meta_access_token_file.read_text(encoding="utf-8").strip()
        return "mock_access_token"

    def get_app_secret(self) -> str | None:
        """Resolve Meta app secret for HMAC webhook verification."""
        if self.meta_app_secret is not None:
            return self.meta_app_secret.get_secret_value()
        if self.meta_app_secret_file is not None and self.meta_app_secret_file.is_file():
            return self.meta_app_secret_file.read_text(encoding="utf-8").strip()
        return None

    def get_webhook_verify_token(self) -> str:
        """Resolve webhook verify token for Hub Challenge validation."""
        if self.meta_webhook_verify_token is not None:
            return self.meta_webhook_verify_token.get_secret_value()
        if (
            self.meta_webhook_verify_token_file is not None
            and self.meta_webhook_verify_token_file.is_file()
        ):
            return self.meta_webhook_verify_token_file.read_text(encoding="utf-8").strip()
        return "vibecore_meta_verify_secret"


settings = WhatsAppSettings()
