"""Pydantic schemas and data models for VibeCore S3 Storage Adapter."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DirectUploadResponse(BaseModel):
    """Result of a direct streaming file upload."""

    model_config = ConfigDict(extra="allow")

    file_id: str = Field(description="Unique file identifier")
    filename: str = Field(description="Original filename")
    content_type: str = Field(description="MIME content type")
    size_bytes: int = Field(description="File size in bytes")
    sha256_hash: str = Field(description="Hexadecimal SHA-256 integrity hash")
    storage_path: str = Field(description="Object key path in the storage bucket")
    created_at: datetime | None = Field(default=None, description="Upload timestamp in UTC")
    etag: str | None = Field(default=None, description="S3 ETag checksum")


class PresignedUploadRequest(BaseModel):
    """Parameters to request a cryptographically signed upload URL."""

    model_config = ConfigDict(extra="allow")

    filename: str = Field(min_length=1, max_length=255, description="Name of the file")
    content_type: str = Field(description="MIME content type")
    file_id: str | None = Field(default=None, description="Optional custom file identifier")
    ttl_seconds: int = Field(
        default=3600, ge=60, le=86400, description="Validity period in seconds"
    )
    sha256_hash: str | None = Field(default=None, description="Optional expected SHA-256 hash")
    custom_metadata: dict[str, str] = Field(
        default_factory=dict, description="Arbitrary custom metadata"
    )


class PresignedUploadResponse(BaseModel):
    """Signed upload URL and upload parameters."""

    model_config = ConfigDict(extra="allow")

    file_id: str = Field(description="Unique file identifier")
    upload_url: str = Field(description="Cryptographically signed temporary upload URL")
    method: str = Field(default="PUT", description="HTTP method to use (PUT)")
    headers: dict[str, str] = Field(
        default_factory=dict, description="Required HTTP headers for upload"
    )
    expires_in_seconds: int = Field(description="Remaining validity duration in seconds")
    storage_path: str = Field(description="Object key in the S3 bucket")


class PresignedDownloadRequest(BaseModel):
    """Parameters to request a cryptographically signed download URL."""

    model_config = ConfigDict(extra="allow")

    file_id: str = Field(min_length=1, description="Unique file identifier to download")
    ttl_seconds: int = Field(
        default=3600, ge=60, le=86400, description="Validity period in seconds"
    )
    download_filename: str | None = Field(
        default=None, description="Optional friendly filename for Content-Disposition"
    )


class PresignedDownloadResponse(BaseModel):
    """Signed download URL."""

    model_config = ConfigDict(extra="allow")

    file_id: str = Field(description="Unique file identifier")
    download_url: str = Field(description="Cryptographically signed temporary download URL")
    expires_in_seconds: int = Field(description="Remaining validity duration in seconds")


class FileMetadataResponse(BaseModel):
    """Metadata of an object stored in S3."""

    model_config = ConfigDict(extra="allow")

    file_id: str = Field(description="Unique file identifier")
    filename: str = Field(description="Original or mapped filename")
    content_type: str = Field(description="MIME content type")
    size_bytes: int = Field(description="File size in bytes")
    sha256_hash: str = Field(description="SHA-256 integrity hash")
    etag: str | None = Field(default=None, description="S3 ETag checksum")
    last_modified: datetime | None = Field(default=None, description="Last modification timestamp")
    custom_metadata: dict[str, str] = Field(default_factory=dict, description="Custom metadata")


class DeleteFileResponse(BaseModel):
    """Confirmation of file deletion."""

    model_config = ConfigDict(extra="allow")

    file_id: str = Field(description="Unique file identifier")
    deleted: bool = Field(description="Deletion confirmation status")
    message: str = Field(description="Status message")


class HealthResponse(BaseModel):
    """Liveness health check response."""

    model_config = ConfigDict(extra="allow")

    status: str = Field(default="ok", description="Liveness status")
    version: str = Field(description="Service version")
    timestamp: datetime | None = Field(default=None, description="Current server timestamp")


class ReadyResponse(BaseModel):
    """Readiness probe response."""

    model_config = ConfigDict(extra="allow")

    status: str = Field(description="Readiness status ('ready' or 'unready')")
    bucket: str = Field(description="Configured S3 bucket")
    storage_connected: bool = Field(description="True if S3 bucket is reachable")
    endpoint: str | None = Field(default=None, description="Connected S3 endpoint URL")
    timestamp: datetime | None = Field(default=None, description="Current server timestamp")
