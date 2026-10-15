"""
Business logic and validation service layer for the Storage Adapter.
"""

import asyncio
from typing import BinaryIO

from app.client import (
    S3StorageClient,
    StorageValidationError,
)
from app.config import Settings
from app.models import (
    DeleteFileResponse,
    DirectUploadResponse,
    FileMetadataResponse,
    PresignedDownloadResponse,
    PresignedUploadResponse,
)


class StorageService:
    def __init__(self, settings: Settings, client: S3StorageClient | None = None):
        self.settings = settings
        self.client = client or S3StorageClient(settings)

    def _validate_content_type(self, content_type: str) -> None:
        clean_type = content_type.split(";")[0].strip().lower()
        if self.settings.allowed_content_types:
            allowed = [ct.lower() for ct in self.settings.allowed_content_types]
            if clean_type not in allowed:
                raise StorageValidationError(
                    f"Content-Type '{clean_type}' ist nicht autorisiert. Zulässige Typen: {', '.join(self.settings.allowed_content_types)}"
                )

    async def upload_file(
        self,
        stream: BinaryIO,
        filename: str,
        content_type: str,
        file_id: str | None = None,
        custom_metadata: dict[str, str] | None = None,
    ) -> DirectUploadResponse:
        self._validate_content_type(content_type)
        return await asyncio.to_thread(
            self.client.upload_stream,
            stream=stream,
            filename=filename,
            content_type=content_type,
            file_id=file_id,
            custom_metadata=custom_metadata,
        )

    async def generate_presigned_upload(
        self,
        filename: str,
        content_type: str,
        file_id: str | None = None,
        ttl_seconds: int = 3600,
        sha256_hash: str | None = None,
        custom_metadata: dict[str, str] | None = None,
    ) -> PresignedUploadResponse:
        self._validate_content_type(content_type)
        if ttl_seconds < 60 or ttl_seconds > 86400:
            raise StorageValidationError(
                "TTL muss zwischen 60 und 86400 Sekunden liegen."
            )

        return await asyncio.to_thread(
            self.client.generate_presigned_upload,
            filename=filename,
            content_type=content_type,
            file_id=file_id,
            ttl_seconds=ttl_seconds,
            sha256_hash=sha256_hash,
            custom_metadata=custom_metadata,
        )

    async def generate_presigned_download(
        self,
        file_id: str,
        ttl_seconds: int = 3600,
        download_filename: str | None = None,
    ) -> PresignedDownloadResponse:
        if ttl_seconds < 60 or ttl_seconds > 86400:
            raise StorageValidationError(
                "TTL muss zwischen 60 und 86400 Sekunden liegen."
            )

        return await asyncio.to_thread(
            self.client.generate_presigned_download,
            file_id=file_id,
            ttl_seconds=ttl_seconds,
            download_filename=download_filename,
        )

    async def get_metadata(self, file_id: str) -> FileMetadataResponse:
        return await asyncio.to_thread(self.client.get_metadata, file_id=file_id)

    async def delete_file(self, file_id: str) -> DeleteFileResponse:
        return await asyncio.to_thread(self.client.delete_file, file_id=file_id)

    async def check_ready(self) -> bool:
        return await asyncio.to_thread(self.client.check_bucket_ready)
