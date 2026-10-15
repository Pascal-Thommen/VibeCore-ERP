"""Typed client for VibeCore S3-compatible Object Storage Adapter."""

from __future__ import annotations

import json
from typing import BinaryIO

import httpx

from vibecore._base import BaseHttpClient
from vibecore.storage.models import (
    DeleteFileResponse,
    DirectUploadResponse,
    FileMetadataResponse,
    HealthResponse,
    PresignedDownloadRequest,
    PresignedDownloadResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
    ReadyResponse,
)


class StorageClient(BaseHttpClient):
    """Client for VibeCore S3-compatible Object Storage microservice."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        super().__init__(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            max_retries=max_retries,
            transport=transport,
        )

    def health(self) -> HealthResponse:
        """Liveness check for storage adapter."""
        resp = self._request("GET", "/health")
        self._raise_for_status(resp, adapter_type="storage")
        return HealthResponse.model_validate(resp.json())

    def ready(self) -> ReadyResponse:
        """Readiness probe verifying S3 storage bucket connectivity."""
        resp = self._request("GET", "/ready")
        self._raise_for_status(resp, adapter_type="storage")
        return ReadyResponse.model_validate(resp.json())

    def upload(
        self,
        file: bytes | BinaryIO,
        filename: str,
        *,
        content_type: str | None = None,
        file_id: str | None = None,
        custom_metadata: dict[str, str] | None = None,
    ) -> DirectUploadResponse:
        """
        Directly stream a file to S3 storage with automatic SHA-256 calculation.
        """
        mimetype = content_type or "application/octet-stream"
        files = {"file": (filename, file, mimetype)}
        form_data: dict[str, str] = {}
        if file_id:
            form_data["file_id"] = file_id
        if custom_metadata:
            form_data["custom_metadata"] = json.dumps(custom_metadata)

        resp = self._request(
            "POST",
            "/api/v1/storage/upload",
            files=files,
            data=form_data if form_data else None,
        )
        self._raise_for_status(resp, adapter_type="storage")
        return DirectUploadResponse.model_validate(resp.json())

    def get_presigned_upload_url(
        self,
        filename: str,
        content_type: str,
        *,
        file_id: str | None = None,
        ttl_seconds: int = 3600,
        sha256_hash: str | None = None,
        custom_metadata: dict[str, str] | None = None,
    ) -> PresignedUploadResponse:
        """
        Generate a cryptographically signed PUT URL for client-direct upload to S3.
        """
        payload = PresignedUploadRequest(
            filename=filename,
            content_type=content_type,
            file_id=file_id,
            ttl_seconds=ttl_seconds,
            sha256_hash=sha256_hash,
            custom_metadata=custom_metadata or {},
        )
        resp = self._request(
            "POST",
            "/api/v1/storage/presigned-upload",
            json=payload.model_dump(exclude_none=True),
        )
        self._raise_for_status(resp, adapter_type="storage")
        return PresignedUploadResponse.model_validate(resp.json())

    def get_presigned_download_url(
        self,
        file_id: str,
        *,
        ttl_seconds: int = 3600,
        download_filename: str | None = None,
    ) -> PresignedDownloadResponse:
        """
        Generate a cryptographically signed GET URL for downloading an object directly from S3.
        """
        payload = PresignedDownloadRequest(
            file_id=file_id,
            ttl_seconds=ttl_seconds,
            download_filename=download_filename,
        )
        resp = self._request(
            "POST",
            "/api/v1/storage/presigned-download",
            json=payload.model_dump(exclude_none=True),
        )
        self._raise_for_status(resp, adapter_type="storage")
        return PresignedDownloadResponse.model_validate(resp.json())

    def get_metadata(self, file_id: str) -> FileMetadataResponse:
        """
        Retrieve metadata and SHA-256 hash of an object stored in S3.
        """
        resp = self._request("GET", f"/api/v1/storage/files/{file_id}/metadata")
        self._raise_for_status(resp, adapter_type="storage")
        return FileMetadataResponse.model_validate(resp.json())

    def delete(self, file_id: str) -> DeleteFileResponse:
        """
        Delete an object from S3 storage.
        """
        resp = self._request("DELETE", f"/api/v1/storage/files/{file_id}")
        self._raise_for_status(resp, adapter_type="storage")
        return DeleteFileResponse.model_validate(resp.json())
