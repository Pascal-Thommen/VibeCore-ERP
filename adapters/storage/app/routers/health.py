"""
Health and readiness probes for VibeCore S3 Storage Adapter.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.config import Settings, get_settings
from app.models import HealthResponse, ReadyResponse
from app.service import StorageService

router = APIRouter(tags=["Health"])


def get_storage_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> StorageService:
    return StorageService(settings)


@router.get("/health", response_model=HealthResponse, summary="Liveness Probe")
async def health_check() -> HealthResponse:
    """
    Returns 200 OK if the microservice process is alive.
    """
    return HealthResponse(status="ok", version="0.1.0")


@router.get("/ready", response_model=ReadyResponse, summary="Readiness Probe")
async def readiness_check(
    response: Response,
    service: Annotated[StorageService, Depends(get_storage_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadyResponse:
    """
    Verifies that the target S3 bucket is accessible and ready to accept requests.
    Returns 503 if the S3 bucket is unreachable.
    """
    is_ready = await service.check_ready()
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(
            status="unready",
            bucket=settings.storage_bucket,
            storage_connected=False,
            endpoint=settings.storage_endpoint_url,
        )

    return ReadyResponse(
        status="ready",
        bucket=settings.storage_bucket,
        storage_connected=True,
        endpoint=settings.storage_endpoint_url,
    )
