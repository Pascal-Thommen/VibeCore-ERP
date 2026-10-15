"""
VibeCore ERP S3 Storage Adapter Microservice (Main Application).
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.audit import (
    get_current_correlation_id,
    log_storage_event,
    set_current_correlation_id,
)
from app.config import settings
from app.models import ErrorResponse
from app.routers import health, storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup lifecycle
    init_cid = f"sys_{uuid.uuid4().hex[:12]}"
    set_current_correlation_id(init_cid)
    log_storage_event(
        "service.started",
        "VibeCore S3 Storage Adapter microservice started successfully",
        data={
            "version": "0.1.0",
            "bucket": settings.storage_bucket,
            "region": settings.storage_region,
            "endpoint_url": settings.storage_endpoint_url,
            "addressing_style": settings.storage_addressing_style,
            "max_upload_size_mb": settings.max_upload_size_bytes // (1024 * 1024),
            "auth_enabled": bool(settings.storage_api_key),
        },
    )
    yield
    # Shutdown lifecycle
    log_storage_event("service.shutdown", "VibeCore S3 Storage Adapter shutting down")


app = FastAPI(
    title="VibeCore S3 Storage Adapter",
    description="High-performance S3-compatible object storage microservice for VibeCore ERP documents, invoices, and blob assets.",
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


# Correlation ID Middleware (Säule 4: Observability)
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    incoming_cid = (
        request.headers.get("x-correlation-id")
        or request.headers.get("x-trace-id")
        or request.headers.get("x-request-id")
        or f"vc_stor_{uuid.uuid4().hex[:16]}"
    )
    set_current_correlation_id(incoming_cid)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = incoming_cid
    return response


# Global Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    cid = get_current_correlation_id()
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error="http_error",
            message=str(exc.detail),
            detail=None,
            trace_id=cid,
        ).model_dump(mode="json"),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    cid = get_current_correlation_id()
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error="validation_error",
            message="Die Anfrage-Parameter oder der Payload entsprechen nicht dem Schema.",
            detail=exc.errors(),
            trace_id=cid,
        ).model_dump(mode="json"),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    cid = get_current_correlation_id()
    log_storage_event(
        "server.unhandled_exception",
        f"Unhandled server error: {exc}",
        level=40,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="internal_error",
            message="Ein interner Serverfehler ist im Objektspeicher-Adapter aufgetreten.",
            detail=str(exc),
            trace_id=cid,
        ).model_dump(mode="json"),
    )


# Register Routers
app.include_router(health.router)
app.include_router(storage.router)
