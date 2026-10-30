"""Double-entry journal entry endpoints for the protected Finance Core."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints._errors import raise_write_error
from app.crud import accounting_crud
from app.db.session import get_async_session
from app.schemas.accounting_schemas import (
    JournalEntryCreate,
    JournalEntryPost,
    JournalEntryRead,
    JournalEntryUpdate,
)

router = APIRouter(prefix="/journal-entries", tags=["journal-entries"])
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


@router.get("", response_model=list[JournalEntryRead])
async def list_journal_entries(
    session: SessionDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
) -> list[JournalEntryRead]:
    return await accounting_crud.list_journal_entries(session, offset=offset, limit=limit)


@router.post("", response_model=JournalEntryRead, status_code=status.HTTP_201_CREATED)
async def create_journal_entry(
    data: JournalEntryCreate, session: SessionDep
) -> JournalEntryRead:
    try:
        return await accounting_crud.create_journal_entry(session, data)
    except Exception as exc:
        await raise_write_error(session, exc)


@router.get("/{journal_entry_id}", response_model=JournalEntryRead)
async def read_journal_entry(journal_entry_id: UUID, session: SessionDep) -> JournalEntryRead:
    journal_entry = await accounting_crud.get_journal_entry(session, journal_entry_id)
    if journal_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="journal entry not found")
    return journal_entry


@router.patch("/{journal_entry_id}", response_model=JournalEntryRead)
async def update_journal_entry(
    journal_entry_id: UUID, data: JournalEntryUpdate, session: SessionDep
) -> JournalEntryRead:
    try:
        journal_entry = await accounting_crud.update_journal_entry(session, journal_entry_id, data)
    except Exception as exc:
        await raise_write_error(session, exc)
    if journal_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="journal entry not found")
    return journal_entry


@router.delete("/{journal_entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_journal_entry(journal_entry_id: UUID, session: SessionDep) -> Response:
    try:
        deleted = await accounting_crud.delete_journal_entry(session, journal_entry_id)
    except Exception as exc:
        await raise_write_error(session, exc)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="journal entry not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{journal_entry_id}/submit", response_model=JournalEntryRead)
async def submit_journal_entry(journal_entry_id: UUID, session: SessionDep) -> JournalEntryRead:
    try:
        journal_entry = await accounting_crud.submit_journal_entry(session, journal_entry_id)
    except Exception as exc:
        await raise_write_error(session, exc)
    if journal_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="journal entry not found")
    return journal_entry


@router.post("/{journal_entry_id}/post", response_model=JournalEntryRead)
async def post_journal_entry(
    journal_entry_id: UUID, data: JournalEntryPost, session: SessionDep
) -> JournalEntryRead:
    try:
        journal_entry = await accounting_crud.post_journal_entry(session, journal_entry_id, data)
    except Exception as exc:
        await raise_write_error(session, exc)
    if journal_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="journal entry not found")
    return journal_entry
