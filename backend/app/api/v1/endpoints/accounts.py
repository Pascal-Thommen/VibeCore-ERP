"""Chart-of-accounts endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints._errors import raise_write_error
from app.crud import core_crud
from app.db.session import get_async_session
from app.schemas.core_schemas import AccountCreate, AccountRead, AccountUpdate

router = APIRouter(prefix="/accounts", tags=["accounts"])
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


@router.get("", response_model=list[AccountRead])
async def list_accounts(
    session: SessionDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
) -> list[AccountRead]:
    return await core_crud.list_accounts(session, offset=offset, limit=limit)


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(data: AccountCreate, session: SessionDep) -> AccountRead:
    try:
        return await core_crud.create_account(session, data)
    except Exception as exc:
        await raise_write_error(session, exc)


@router.get("/{account_id}", response_model=AccountRead)
async def read_account(account_id: UUID, session: SessionDep) -> AccountRead:
    account = await core_crud.get_account(session, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
    return account


@router.patch("/{account_id}", response_model=AccountRead)
async def update_account(account_id: UUID, data: AccountUpdate, session: SessionDep) -> AccountRead:
    try:
        account = await core_crud.update_account(session, account_id, data)
    except Exception as exc:
        await raise_write_error(session, exc)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: UUID, session: SessionDep) -> Response:
    try:
        deleted = await core_crud.delete_account(session, account_id)
    except Exception as exc:
        await raise_write_error(session, exc)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
