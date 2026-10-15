"""
Storage router exposing direct uploads, presigned URLs, metadata, and deletions.
"""

import json
import secrets
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Security,
    UploadFile,
    status,
)
from fastapi.security.api_key import APIKeyHeader

from app.client import (
    StorageAuthenticationError,
    StorageConnectionError,
    StorageError,
    StorageNotFoundError,
    StorageValidationError,
)
from app.config import Settings, get_settings
from app.models import (
    DeleteFileResponse,
    DirectUploadResponse,
    FileMetadataResponse,
    PresignedDownloadRequest,
    PresignedDownloadResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
)
from app.service import StorageService

router = APIRouter(prefix="/api/v1/storage", tags=["Storage"])

api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_storage_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> StorageService:
    return StorageService(settings)


async def verify_api_key(
    api_key: Annotated[str | None, Security(api_key_header_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """
    Enforces X-API-Key header authentication if STORAGE_API_KEY is configured.
    """
    if settings.storage_api_key and (
        not api_key or not secrets.compare_digest(api_key, settings.storage_api_key)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger oder fehlender API-Key im Header 'X-API-Key'.",
        )


@router.post(
    "/upload",
    response_model=DirectUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
    summary="Direct Streaming Upload",
)
async def upload_file(
    file: Annotated[UploadFile, File(description="File to upload via streaming.")],
    file_id: Annotated[
        str | None, Form(description="Optional custom file path or identifier.")
    ] = None,
    custom_metadata: Annotated[
        str | None,
        Form(description="Optional JSON-encoded dictionary of custom metadata."),
    ] = None,
    service: Annotated[StorageService, Depends(get_storage_service)] = None,
) -> DirectUploadResponse:
    """
    Uploads a document directly to S3 via streaming.
    Calculates SHA-256 hash on-the-fly and saves integrity metadata on the object.
    """
    meta_dict = None
    if custom_metadata:
        try:
            parsed = json.loads(custom_metadata)
            if isinstance(parsed, dict):
                meta_dict = {str(k): str(v) for k, v in parsed.items()}
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiges JSON-Format im Feld custom_metadata: {e}",
            ) from e

    content_type = file.content_type or "application/octet-stream"
    original_filename = file.filename or "uploaded.bin"

    try:
        return await service.upload_file(
            stream=file.file,
            filename=original_filename,
            content_type=content_type,
            file_id=file_id,
            custom_metadata=meta_dict,
        )
    except StorageValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    except StorageAuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except StorageConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
        ) from e
    except StorageError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload fehlgeschlagen: {e}",
        ) from e


@router.post(
    "/presigned-upload",
    response_model=PresignedUploadResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Generate Presigned Upload URL",
)
async def create_presigned_upload(
    payload: PresignedUploadRequest,
    service: Annotated[StorageService, Depends(get_storage_service)],
) -> PresignedUploadResponse:
    """
    Generates a cryptographically signed PUT URL for direct client-to-storage upload.
    Offloads bandwidth and CPU from the application server.
    """
    try:
        return await service.generate_presigned_upload(
            filename=payload.filename,
            content_type=payload.content_type,
            file_id=payload.file_id,
            ttl_seconds=payload.ttl_seconds or 3600,
            sha256_hash=payload.sha256_hash,
            custom_metadata=payload.custom_metadata,
        )
    except StorageValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    except StorageAuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except StorageConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
        ) from e
    except StorageError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e


@router.post(
    "/presigned-download",
    response_model=PresignedDownloadResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Generate Presigned Download URL",
)
async def create_presigned_download(
    payload: PresignedDownloadRequest,
    service: Annotated[StorageService, Depends(get_storage_service)],
) -> PresignedDownloadResponse:
    """
    Generates a cryptographically signed GET URL for downloading files directly from storage.
    """
    try:
        return await service.generate_presigned_download(
            file_id=payload.file_id,
            ttl_seconds=payload.ttl_seconds or 3600,
            download_filename=payload.download_filename,
        )
    except StorageValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    except StorageNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except StorageAuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except StorageConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
        ) from e
    except StorageError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e


@router.get(
    "/files/{file_id:path}/metadata",
    response_model=FileMetadataResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Get File Metadata",
)
async def get_file_metadata(
    file_id: str,
    service: Annotated[StorageService, Depends(get_storage_service)],
) -> FileMetadataResponse:
    """
    Retrieves file metadata from S3 including size, Content-Type, ETag, and SHA-256 integrity hash.
    """
    try:
        return await service.get_metadata(file_id=file_id)
    except StorageValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    except StorageNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except StorageAuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except StorageConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
        ) from e
    except StorageError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e


@router.delete(
    "/files/{file_id:path}",
    response_model=DeleteFileResponse,
    dependencies=[Depends(verify_api_key)],
    summary="Delete File",
)
async def delete_file(
    file_id: str,
    service: Annotated[StorageService, Depends(get_storage_service)],
) -> DeleteFileResponse:
    """
    Deletes an object from S3 storage after confirming its existence.
    """
    try:
        return await service.delete_file(file_id=file_id)
    except StorageValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
    except StorageNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except StorageAuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except StorageConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
        ) from e
    except StorageError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e
