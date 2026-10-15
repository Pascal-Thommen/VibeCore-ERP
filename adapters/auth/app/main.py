"""
VibeCore ERP - Google OAuth 2.0 & OIDC SSO Microservice (Main Application).
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.audit import get_current_trace_id, log_audit_event, set_current_trace_id
from app.config import settings
from app.models import ErrorResponse
from app.routers import auth, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    set_current_trace_id(f"sys_{uuid.uuid4().hex[:12]}")
    log_audit_event(
        "service.started",
        "VibeCore Auth Adapter microservice started successfully",
        data={
            "version": "0.1.0",
            "google_client_id": settings.google_client_id,
            "google_redirect_uri": settings.google_redirect_uri,
            "jwt_issuer": settings.jwt_issuer,
            "jwt_audience": settings.jwt_audience,
        },
    )
    yield
    # Shutdown
    log_audit_event("service.shutdown", "VibeCore Auth Adapter microservice shutting down")


app = FastAPI(
    title="VibeCore Auth Adapter",
    description="Isolated Google OAuth 2.0 & OpenID Connect (OIDC) SSO Microservice for VibeCore ERP.",
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


# Trace ID Correlation Middleware (Säule 4: Observability)
@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    incoming_tid = (
        request.headers.get("x-trace-id")
        or request.headers.get("x-request-id")
        or f"vc_tr_{uuid.uuid4().hex[:16]}"
    )
    set_current_trace_id(incoming_tid)
    response = await call_next(request)
    response.headers["X-Trace-Id"] = incoming_tid
    return response


# Global Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    tid = get_current_trace_id()
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
