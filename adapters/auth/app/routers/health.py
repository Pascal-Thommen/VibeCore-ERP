"""
VibeCore ERP Auth Adapter - Health & Readiness Routers (Säule 4: Observability).
"""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.config import settings
from app.models import HealthResponse, ReadinessResponse

router = APIRouter(tags=["Observability & Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness and Healthcheck",
    description="Returns current health state, service version, and OAuth configuration status.",
)
async def get_health() -> HealthResponse:
    google_configured = bool(
        settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri
    )
    return HealthResponse(
        status="healthy",
        service="vibecore-auth-adapter",
        version="0.1.0",
        google_oauth_configured=google_configured,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness Check",
    description="Verifies that all required cryptographic secrets and configuration parameters are loaded.",
)
async def get_readiness() -> ReadinessResponse:
    checks = {
        "google_credentials": bool(settings.google_client_id and settings.google_client_secret),
        "jwt_secret": bool(len(settings.jwt_secret) >= 32),
        "cookie_secret": bool(len(settings.cookie_secret) >= 32),
        "redirect_uri": bool(settings.google_redirect_uri),
    }
    all_ready = all(checks.values())
    return ReadinessResponse(
        status="ready" if all_ready else "not_ready",
        checks=checks,
        timestamp=datetime.now(UTC).isoformat(),
    )
