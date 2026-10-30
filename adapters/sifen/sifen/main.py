"""
FastAPI application entrypoint for VibeCore SIFEN Fiscal Adapter.
Includes lifespan context, observability middleware, and health/readiness endpoints.
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from sqlalchemy import text

from sifen.config import settings
from sifen.database import engine, init_db
from sifen.router import router

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("sifen.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing SIFEN Fiscal Adapter persistent Outbox schema...")
    init_db()
    logger.info(
        "SIFEN Adapter started. Environment=%s BaseURL=%s",
        settings.sifen_env,
        settings.resolved_base_url,
    )
    yield
    logger.info("Shutting down SIFEN Adapter.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="VibeCore SIFEN Adapter API",
        version="1.0.0",
        description="Isolated adapter service for Paraguayan SIFEN electronic invoicing, dynamic DTE resolution, and persistent Outbox transmission.",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        start_time = time.time()
        response: Response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Process-Time"] = f"{process_time:.4f}s"
        return response

    @app.get("/health", tags=["Observability"], status_code=status.HTTP_200_OK)
    def health_check():
        return {
            "status": "healthy",
            "service": "sifen-adapter",
            "version": "1.0.0",
            "environment": settings.sifen_env,
        }

    @app.get("/ready", tags=["Observability"], status_code=status.HTTP_200_OK)
    def readiness_check():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception as exc:
            logger.error("Readiness check DB failure: %s", exc)
            db_status = f"error: {exc}"

        ready = db_status == "connected" and bool(settings.resolved_base_url)
        return {
            "ready": ready,
            "database": db_status,
            "sifen_endpoint": settings.resolved_base_url,
        }

    app.include_router(router)
    return app


app = create_app()
