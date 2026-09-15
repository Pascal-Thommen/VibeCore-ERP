from fastapi import FastAPI

from app.api.router import api_router
from app.api.v1.router import core_router
from app.core.config import settings

app = FastAPI(
    title="VibeCore ERP API",
    version="0.1.0",
    description="Headless Finance Core API for VibeCore ERP.",
)

app.include_router(api_router, prefix=settings.api_v1_prefix)
app.include_router(core_router, prefix=settings.api_v1_prefix)
