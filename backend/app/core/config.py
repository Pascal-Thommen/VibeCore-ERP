from functools import cached_property
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables or an ignored local .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"

    database_url: str | None = None
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "vibecore"
    database_user: str = "vibecore"
    database_password: SecretStr | None = None
    database_password_file: Path | None = None

    @cached_property
    def sqlalchemy_database_url(self) -> str:
        """Return an SQLAlchemy psycopg URL without logging its secret component."""
        if self.database_url:
            return self.database_url

        password = self._database_password()
        return (
            "postgresql+psycopg://"
            f"{quote_plus(self.database_user)}:{quote_plus(password)}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )

    def _database_password(self) -> str:
        if self.database_password is not None:
            return self.database_password.get_secret_value()

        if self.database_password_file is not None:
            try:
                return self.database_password_file.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise RuntimeError("DATABASE_PASSWORD_FILE could not be read") from exc

        raise RuntimeError("Set DATABASE_URL, DATABASE_PASSWORD, or DATABASE_PASSWORD_FILE")


settings = Settings()
