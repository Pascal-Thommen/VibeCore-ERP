"""
FastAPI application entrypoint for VibeCore Stripe Payment Adapter.
Includes lifespan context, observability middleware, and health endpoints.
"""

from contextlib import asynccontextmanager
import logging
import time
import uuid
from fastapi import FastAPI, Request, Response, status
from sqlalchemy import text

from stripe_adapter.config import settings
from stripe_adapter.database import engine, init_db
from stripe_adapter.router import router

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("stripe_adapter.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Stripe Payment Adapter database schema...")
    init_db()
    logger.info("Stripe Adapter started. Environment=%s BaseURL=%s", settings.stripe_env, settings.resolved_base_url)
    yield
    logger.info("Shutting down Stripe Adapter.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="VibeCore Stripe Payment Adapter",
        version="1.0.0",
        description="Autonomous, resilient payment adapter for Stripe international gateway.",
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
            "service": "stripe-adapter",
            "version": "1.0.0",
            "environment": settings.stripe_env,
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

        ready = (
            db_status == "connected"
            and bool(settings.stripe_secret_key)
            and bool(settings.stripe_webhook_secret)
        )

        return {
            "ready": ready,
            "database": db_status,
            "gateway_configured": bool(settings.stripe_secret_key and settings.stripe_webhook_secret),
        }

    app.include_router(router)
    return app


app = create_app()
