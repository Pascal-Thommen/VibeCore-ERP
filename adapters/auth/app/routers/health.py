"""
VibeCore ERP Auth Adapter - Health, Readiness, and Prometheus Metrics (Säule 4: Observability).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Response

from app.config import settings
from app.crypto import crypto_manager
from app.metrics import metrics_registry
from app.models import HealthResponse, ReadinessResponse

router = APIRouter(tags=["Observability & Health"])


@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Liveness and Healthcheck (Kubernetes standard)",
    description="Returns current health state, service version, and OAuth configuration status.",
)
async def get_healthz() -> HealthResponse:
    google_configured = bool(
        settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri
    )
    return HealthResponse(
        status="healthy",
        service="vibecore-auth-adapter",
        version="0.1.0",
        google_oauth_configured=google_configured,
        timestamp=datetime.now(UTC).isoformat(),
        meta={"algorithm": settings.jwt_algorithm, "key_id": settings.jwt_key_id},
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Healthcheck (Legacy alias for /healthz)",
    description="Returns current health state for backwards compatibility.",
)
async def get_health() -> HealthResponse:
    return await get_healthz()


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    summary="Readiness Check (Kubernetes standard)",
    description="Verifies that all required cryptographic secrets, keys, and configuration parameters are loaded.",
)
async def get_readyz() -> ReadinessResponse:
    # Verify cryptographic keypair is loaded and functional
    has_valid_crypto = False
    try:
        jwks = crypto_manager.get_jwks()
        has_valid_crypto = bool(jwks and "keys" in jwks and len(jwks["keys"]) > 0)
    except Exception:
        has_valid_crypto = False

    checks = {
        "google_credentials": bool(settings.google_client_id and settings.google_client_secret),
        "asymmetric_crypto_keys": has_valid_crypto,
        "cookie_secret": bool(len(settings.cookie_secret) >= 32),
        "redirect_uri": bool(settings.google_redirect_uri),
    }
    all_ready = all(checks.values())
    return ReadinessResponse(
        status="ready" if all_ready else "not_ready",
        checks=checks,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness Check (Legacy alias for /readyz)",
)
async def get_ready() -> ReadinessResponse:
    return await get_readyz()


@router.get(
    "/metrics",
    summary="Prometheus Metrics Endpoint",
    description="Returns runtime metrics formatted for Prometheus scrapers in text/plain format.",
)
async def get_metrics():
    content = metrics_registry.generate_prometheus_text()
    return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")
