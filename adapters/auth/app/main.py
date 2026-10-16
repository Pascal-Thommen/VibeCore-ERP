"""
VibeCore ERP - Google OAuth 2.0 & OIDC SSO Microservice (Main Application).
Provides standalone IdP capabilities, RS256 JWKS endpoints, PKCE, multi-tenancy, and observability.
"""

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.audit import get_current_trace_id, log_audit_event, set_current_trace_id
from app.config import settings
from app.crypto import crypto_manager
from app.metrics import metrics_registry
from app.models import ErrorResponse, JWKSResponse, OpenIDConfigurationResponse
from app.routers import auth, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    set_current_trace_id(f"sys_{uuid.uuid4().hex[:12]}")
    log_audit_event(
        "service.started",
        "VibeCore Auth IdP microservice started successfully",
        data={
            "version": "0.1.0",
            "google_client_id": settings.google_client_id,
            "google_redirect_uri": settings.google_redirect_uri,
            "jwt_issuer": settings.jwt_issuer,
            "jwt_audience": settings.jwt_audience,
            "jwt_algorithm": settings.jwt_algorithm,
            "jwt_key_id": settings.jwt_key_id,
        },
    )
    yield
    # Shutdown
    log_audit_event("service.shutdown", "VibeCore Auth IdP microservice shutting down")


app = FastAPI(
    title="VibeCore Auth Microservice",
    description="Standalone Google OAuth 2.0 Identity Provider (IdP) for VibeCore ERP and AIBill with PKCE, RS256/EdDSA asymmetric tokens, JWKS, multi-tenancy, and Prometheus metrics.",
    version="0.1.0",
    lifespan=lifespan,
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Trace ID Correlation & Metrics Middleware (Säule 4: Observability)
@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    incoming_tid = (
        request.headers.get("x-trace-id")
        or request.headers.get("x-request-id")
        or f"vc_tr_{uuid.uuid4().hex[:16]}"
    )
    set_current_trace_id(incoming_tid)
    start_time = time.time()

    response = await call_next(request)

    response.headers["X-Trace-Id"] = incoming_tid
    metrics_registry.record_http_request(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
    )
    return response


# Root-level OpenID Connect & JWKS Discovery Endpoints (RFC 8414 & RFC 7517)
@app.get(
    "/.well-known/jwks.json",
    response_model=JWKSResponse,
    tags=["OIDC Discovery & JWKS"],
    summary="Root JWKS endpoint for stateless token validation",
)
async def root_jwks():
    jwks = crypto_manager.get_jwks()
    return JWKSResponse(keys=jwks["keys"])


@app.get(
    "/.well-known/openid-configuration",
    response_model=OpenIDConfigurationResponse,
    tags=["OIDC Discovery & JWKS"],
    summary="OpenID Connect Discovery Configuration",
)
async def openid_configuration():
    base_url = "http://localhost:8001"
    return OpenIDConfigurationResponse(
        issuer=settings.jwt_issuer,
        authorization_endpoint=f"{base_url}/auth/google/login",
        token_endpoint=f"{base_url}/auth/google/callback",
        jwks_uri=f"{base_url}/.well-known/jwks.json",
        userinfo_endpoint=f"{base_url}/auth/me",
        response_types_supported=["code"],
        subject_types_supported=["public"],
        id_token_signing_alg_values_supported=[settings.jwt_algorithm],
    )


# Global Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    tid = get_current_trace_id()
    metrics_registry.record_exception(f"HTTP_{exc.status_code}")
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error="http_error",
            message=str(exc.detail),
            detail=None,
            trace_id=tid,
        ).model_dump(),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    tid = get_current_trace_id()
    metrics_registry.record_exception(type(exc).__name__)
    log_audit_event("server.unhandled_exception", f"Unhandled error: {exc}", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="internal_error",
            message="Ein interner Serverfehler ist aufgetreten.",
            detail=str(exc),
            trace_id=tid,
        ).model_dump(),
    )


# Include Routers
app.include_router(health.router)
app.include_router(auth.router)
