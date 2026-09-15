from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_session

api_router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str


@api_router.get("/health", response_model=HealthResponse, summary="Liveness check")
def health() -> HealthResponse:
    """Report that the API process is running without requiring a database call."""
    return HealthResponse(status="ok")


@api_router.get("/ready", response_model=HealthResponse, summary="Readiness check")
def ready(session: Session = Depends(get_session)) -> HealthResponse:
    """Report readiness only when PostgreSQL can serve a query."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database is unavailable",
        ) from exc

    return HealthResponse(status="ready")
