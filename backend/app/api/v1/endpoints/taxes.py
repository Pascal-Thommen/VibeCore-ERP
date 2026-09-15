"""Paraguayan IVA master-data endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints._errors import raise_write_error
from app.crud import core_crud
from app.db.session import get_async_session
from app.schemas.core_schemas import TaxCreate, TaxRead, TaxUpdate

router = APIRouter(prefix="/taxes", tags=["taxes"])
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


@router.get("", response_model=list[TaxRead])
async def list_taxes(
    session: SessionDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
) -> list[TaxRead]:
    return await core_crud.list_taxes(session, offset=offset, limit=limit)


@router.post("", response_model=TaxRead, status_code=status.HTTP_201_CREATED)
async def create_tax(data: TaxCreate, session: SessionDep) -> TaxRead:
    try:
        return await core_crud.create_tax(session, data)
    except Exception as exc:
        await raise_write_error(session, exc)


@router.get("/{tax_id}", response_model=TaxRead)
async def read_tax(tax_id: UUID, session: SessionDep) -> TaxRead:
    tax = await core_crud.get_tax(session, tax_id)
    if tax is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tax not found")
    return tax


@router.patch("/{tax_id}", response_model=TaxRead)
async def update_tax(tax_id: UUID, data: TaxUpdate, session: SessionDep) -> TaxRead:
    try:
        tax = await core_crud.update_tax(session, tax_id, data)
    except Exception as exc:
        await raise_write_error(session, exc)
    if tax is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tax not found")
    return tax


@router.delete("/{tax_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tax(tax_id: UUID, session: SessionDep) -> Response:
    try:
        deleted = await core_crud.delete_tax(session, tax_id)
    except Exception as exc:
        await raise_write_error(session, exc)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tax not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
