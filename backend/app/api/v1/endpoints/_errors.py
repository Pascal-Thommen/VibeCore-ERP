"""HTTP translation for persistence and domain errors.

Keeping this at the router boundary prevents the CRUD layer from depending on
FastAPI while giving every resource endpoint identical error semantics.
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.accounting_crud import JournalEntryNotEditableError, JournalEntryStateError
from app.crud.core_crud import (
    DocumentNotEditableError,
    PartnerDirectionError,
    RelatedResourceNotFoundError,
    TaxScopeError,
)


async def raise_write_error(session: AsyncSession, exc: Exception) -> NoReturn:
    """Map expected persistence failures without leaking database details."""
    if isinstance(exc, IntegrityError):
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="operation conflicts with an existing or referenced Core record",
        ) from exc
    if isinstance(
        exc, (DocumentNotEditableError, JournalEntryNotEditableError, JournalEntryStateError)
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, RelatedResourceNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if isinstance(exc, (PartnerDirectionError, TaxScopeError, ValueError)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    raise exc
