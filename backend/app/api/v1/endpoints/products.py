"""Product and service master-data endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints._errors import raise_write_error
from app.crud import core_crud
from app.db.session import get_async_session
from app.schemas.core_schemas import ProductCreate, ProductRead, ProductUpdate

router = APIRouter(prefix="/products", tags=["products"])
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


@router.get("", response_model=list[ProductRead])
async def list_products(
    session: SessionDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=100),
) -> list[ProductRead]:
    return await core_crud.list_products(session, offset=offset, limit=limit)


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(data: ProductCreate, session: SessionDep) -> ProductRead:
    try:
        return await core_crud.create_product(session, data)
    except Exception as exc:
        await raise_write_error(session, exc)


@router.get("/{product_id}", response_model=ProductRead)
async def read_product(product_id: UUID, session: SessionDep) -> ProductRead:
    product = await core_crud.get_product(session, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
    return product


@router.patch("/{product_id}", response_model=ProductRead)
async def update_product(product_id: UUID, data: ProductUpdate, session: SessionDep) -> ProductRead:
    try:
        product = await core_crud.update_product(session, product_id, data)
    except Exception as exc:
        await raise_write_error(session, exc)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: UUID, session: SessionDep) -> Response:
    try:
        deleted = await core_crud.delete_product(session, product_id)
    except Exception as exc:
        await raise_write_error(session, exc)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
