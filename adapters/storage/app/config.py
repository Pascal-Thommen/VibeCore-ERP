"""
Configuration settings for the VibeCore S3 Storage Adapter.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    storage_endpoint_url: str | None = Field(
        default=None,
        validation_alias="STORAGE_ENDPOINT_URL",
        description="Custom endpoint URL for S3 provider (e.g. MinIO, Cloudflare R2, Wasabi). None for AWS S3.",
    )
    storage_public_endpoint_url: str | None = Field(
        default=None,
        validation_alias="STORAGE_PUBLIC_ENDPOINT_URL",
        description="Public endpoint URL for presigned URLs when the service runs inside Docker or behind NAT.",
    )
    storage_access_key: str = Field(
        default="minioadmin",
        validation_alias="STORAGE_ACCESS_KEY",
        description="S3 Access Key ID.",
    )
    storage_secret_key: str = Field(
        default="minioadmin",
        validation_alias="STORAGE_SECRET_KEY",
        description="S3 Secret Access Key.",
    )
    storage_bucket: str = Field(
        default="vibecore-documents",
        validation_alias="STORAGE_BUCKET",
        description="Target S3 Bucket name.",
    )
    storage_region: str = Field(
        default="us-east-1",
        validation_alias="STORAGE_REGION",
        description="S3 Region name.",
    )
    storage_addressing_style: str = Field(
        default="auto",
        validation_alias="STORAGE_ADDRESSING_STYLE",
        description="S3 addressing style ('auto', 'path', 'virtual'). Path style is required for MinIO.",
    )
    storage_api_key: str | None = Field(
        default=None,
        validation_alias="STORAGE_API_KEY",
        description="Optional API Key to secure adapter endpoints. Enforced via X-API-Key header when set.",
    )
    default_presigned_ttl_seconds: int = Field(
        default=3600,
        validation_alias="STORAGE_DEFAULT_PRESIGNED_TTL",
        description="Default TTL in seconds for presigned URLs (1 hour).",
    )
    max_upload_size_bytes: int = Field(
        default=52428800,
        validation_alias="STORAGE_MAX_UPLOAD_SIZE_BYTES",
        description="Maximum allowed direct upload size in bytes (default: 50MB).",
    )
    connect_timeout_seconds: float = Field(
        default=5.0,
        validation_alias="STORAGE_CONNECT_TIMEOUT",
        description="Socket connection timeout for S3 calls.",
    )
    read_timeout_seconds: float = Field(
        default=30.0,
        validation_alias="STORAGE_READ_TIMEOUT",
        description="Socket read timeout for S3 calls.",
    )
    max_retries: int = Field(
        default=3,
        validation_alias="STORAGE_MAX_RETRIES",
        description="Maximum automatic retries for transient S3 network failures.",
    )
    allowed_content_types: list[str] = Field(
        default=[
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/tiff",
            "application/xml",
            "text/xml",
            "application/json",
            "text/csv",
            "text/plain",
        ],
        validation_alias="STORAGE_ALLOWED_CONTENT_TYPES",
        description="Whitelist of allowed MIME types for document uploads.",
    )
    allowed_origins: list[str] = Field(
        default=["*"],
        validation_alias="STORAGE_ALLOWED_ORIGINS",
        description="CORS allowed origins.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
