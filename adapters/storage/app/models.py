"""
Pydantic schemas and data transfer objects for the VibeCore S3 Storage Adapter.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class DirectUploadResponse(BaseModel):
    file_id: str = Field(..., description="Unique file identifier.")
    filename: str = Field(..., description="Original filename.")
    content_type: str = Field(..., description="MIME content type.")
    size_bytes: int = Field(..., description="File size in bytes.")
    sha256_hash: str = Field(..., description="Hexadecimal SHA-256 integrity hash.")
    storage_path: str = Field(..., description="Object key path in the storage bucket.")
    created_at: datetime = Field(
        default_factory=utc_now, description="Upload timestamp in UTC."
    )
    etag: str | None = Field(default=None, description="S3 ETag checksum.")


class PresignedUploadRequest(BaseModel):
    filename: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the file to be uploaded.",
    )
    content_type: str = Field(..., description="MIME content type of the file.")
    file_id: str | None = Field(
        default=None,
        description="Optional custom file identifier. Must be safe path characters.",
    )
    ttl_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Validity period in seconds (60s to 24h).",
    )
    sha256_hash: str | None = Field(
        default=None, description="Optional expected SHA-256 hash for client integrity."
    )
    custom_metadata: dict[str, str] = Field(
        default_factory=dict, description="Arbitrary custom metadata key-values."
    )

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        clean = v.strip().replace("\\", "/").split("/")[-1]
        if not clean or clean in (".", ".."):
            raise ValueError("Ungültiger Dateiname")
        return clean


class PresignedUploadResponse(BaseModel):
    file_id: str = Field(..., description="Unique file identifier.")
    upload_url: str = Field(
        ..., description="Cryptographically signed temporary upload URL."
    )
    method: str = Field(
        default="PUT", description="HTTP method to use for the upload (PUT)."
    )
    headers: dict[str, str] = Field(
        default_factory=dict, description="Required HTTP headers for the direct upload."
    )
    expires_in_seconds: int = Field(
        ..., description="Remaining validity duration in seconds."
    )
    storage_path: str = Field(..., description="Object key in the S3 bucket.")


class PresignedDownloadRequest(BaseModel):
    file_id: str = Field(
        ..., min_length=1, description="Unique file identifier to download."
    )
    ttl_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Validity period in seconds (60s to 24h).",
    )
    download_filename: str | None = Field(
        default=None, description="Optional friendly filename for Content-Disposition."
    )


class PresignedDownloadResponse(BaseModel):
    file_id: str = Field(..., description="Unique file identifier.")
    download_url: str = Field(
        ..., description="Cryptographically signed temporary download URL."
    )
    expires_in_seconds: int = Field(
        ..., description="Remaining validity duration in seconds."
    )


class FileMetadataResponse(BaseModel):
    file_id: str = Field(..., description="Unique file identifier.")
    filename: str = Field(..., description="Original or mapped filename.")
    content_type: str = Field(..., description="MIME content type.")
    size_bytes: int = Field(..., description="File size in bytes.")
    sha256_hash: str = Field(..., description="SHA-256 integrity hash.")
    etag: str | None = Field(default=None, description="S3 ETag checksum.")
    last_modified: datetime | None = Field(
        default=None, description="Last modification timestamp."
    )
    custom_metadata: dict[str, str] = Field(
        default_factory=dict, description="User or system defined metadata."
    )


class DeleteFileResponse(BaseModel):
    file_id: str = Field(..., description="Unique file identifier.")
    deleted: bool = Field(..., description="Deletion confirmation status.")
    message: str = Field(..., description="Status message.")


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Liveness status.")
    version: str = Field(..., description="Service version.")
    timestamp: datetime = Field(
        default_factory=utc_now, description="Current server timestamp."
    )


class ReadyResponse(BaseModel):
    status: str = Field(..., description="Readiness status ('ready' or 'unready').")
    bucket: str = Field(..., description="Configured S3 bucket.")
    storage_connected: bool = Field(..., description="True if S3 bucket is reachable.")
    endpoint: str | None = Field(default=None, description="Connected S3 endpoint URL.")
    timestamp: datetime = Field(
        default_factory=utc_now, description="Current server timestamp."
    )


class ErrorResponse(BaseModel):
    error: str = Field(..., description="Error category code.")
    message: str = Field(..., description="Human readable error message.")
    detail: Any | None = Field(
        default=None, description="Additional error context or debug information."
    )
    trace_id: str = Field(..., description="Correlation / Trace ID for observability.")
    timestamp: datetime = Field(
        default_factory=utc_now, description="Timestamp of the error in UTC."
    )
