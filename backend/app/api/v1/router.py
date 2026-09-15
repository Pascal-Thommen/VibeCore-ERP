"""Aggregate router for version 1 Core resources."""

from fastapi import APIRouter

from app.api.v1.endpoints import accounts, documents, journal_entries, partners, products, taxes

core_router = APIRouter()
core_router.include_router(partners.router)
core_router.include_router(accounts.router)
core_router.include_router(taxes.router)
core_router.include_router(products.router)
core_router.include_router(documents.router)
core_router.include_router(journal_entries.router)
