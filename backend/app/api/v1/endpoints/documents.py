"""Commercial document and line-item endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints._errors import raise_write_error
from app.crud import core_crud
from app.db.session import get_async_session
from app.schemas.core_schemas import (
    DocumentCreate,
    DocumentItemCreate,
    DocumentItemRead,
    DocumentItemUpdate,
    DocumentRead,
    DocumentUpdate,
)

router = APIRouter(prefix="/documents", tags=["documents"])
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    session: SessionDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
) -> list[DocumentRead]:
    return await core_crud.list_documents(session, offset=offset, limit=limit)


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def create_document(data: DocumentCreate, session: SessionDep) -> DocumentRead:
    try:
        return await core_crud.create_document(session, data)
    except Exception as exc:
        await raise_write_error(session, exc)


@router.get("/items/{item_id}", response_model=DocumentItemRead)
async def read_document_item(item_id: UUID, session: SessionDep) -> DocumentItemRead:
    item = await core_crud.get_document_item(session, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document item not found")
    return item


@router.patch("/items/{item_id}", response_model=DocumentItemRead)
async def update_document_item(
    item_id: UUID, data: DocumentItemUpdate, session: SessionDep
) -> DocumentItemRead:
    try:
        item = await core_crud.update_document_item(session, item_id, data)
    except Exception as exc:
        await raise_write_error(session, exc)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document item not found")
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_item(item_id: UUID, session: SessionDep) -> Response:
    try:
        deleted = await core_crud.delete_document_item(session, item_id)
    except Exception as exc:
        await raise_write_error(session, exc)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document item not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{document_id}", response_model=DocumentRead)
async def read_document(document_id: UUID, session: SessionDep) -> DocumentRead:
    document = await core_crud.get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return document


@router.patch("/{document_id}", response_model=DocumentRead)
async def update_document(
    document_id: UUID, data: DocumentUpdate, session: SessionDep
) -> DocumentRead:
    try:
        document = await core_crud.update_document(session, document_id, data)
    except Exception as exc:
        await raise_write_error(session, exc)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: UUID, session: SessionDep) -> Response:
    try:
        deleted = await core_crud.delete_document(session, document_id)
    except Exception as exc:
        await raise_write_error(session, exc)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{document_id}/items",
    response_model=DocumentItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_document_item(
    document_id: UUID, data: DocumentItemCreate, session: SessionDep
) -> DocumentItemRead:
    try:
        item = await core_crud.add_document_item(session, document_id, data)
    except Exception as exc:
        await raise_write_error(session, exc)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return item
