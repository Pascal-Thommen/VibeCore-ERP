"""Partner master-data endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints._errors import raise_write_error
from app.crud import core_crud
from app.db.session import get_async_session
from app.schemas.core_schemas import PartnerCreate, PartnerRead, PartnerUpdate

router = APIRouter(prefix="/partners", tags=["partners"])
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


@router.get("", response_model=list[PartnerRead])
async def list_partners(
    session: SessionDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
) -> list[PartnerRead]:
    return await core_crud.list_partners(session, offset=offset, limit=limit)


@router.post("", response_model=PartnerRead, status_code=status.HTTP_201_CREATED)
async def create_partner(data: PartnerCreate, session: SessionDep) -> PartnerRead:
    try:
        return await core_crud.create_partner(session, data)
    except Exception as exc:
        await raise_write_error(session, exc)


@router.get("/{partner_id}", response_model=PartnerRead)
async def read_partner(partner_id: UUID, session: SessionDep) -> PartnerRead:
    partner = await core_crud.get_partner(session, partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="partner not found")
    return partner


@router.patch("/{partner_id}", response_model=PartnerRead)
async def update_partner(partner_id: UUID, data: PartnerUpdate, session: SessionDep) -> PartnerRead:
    try:
        partner = await core_crud.update_partner(session, partner_id, data)
    except Exception as exc:
        await raise_write_error(session, exc)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="partner not found")
    return partner


@router.delete("/{partner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_partner(partner_id: UUID, session: SessionDep) -> Response:
    try:
        deleted = await core_crud.delete_partner(session, partner_id)
    except Exception as exc:
        await raise_write_error(session, exc)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="partner not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
