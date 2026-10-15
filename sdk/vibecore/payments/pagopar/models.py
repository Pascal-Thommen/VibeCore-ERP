"""Pydantic schemas and data models for Pagopar Payment Gateway Adapter."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentType(StrEnum):
    CI = "CI"
    RUC = "RUC"
    PAS = "PAS"


class OrderStatus(StrEnum):
    INITIATED = "INITIATED"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BuyerModel(BaseModel):
    """Customer profile details for Pagopar order."""

    model_config = ConfigDict(extra="allow")

    ruc: str = Field(description="Tax identification or identification number")
    email: str = Field(description="Buyer email address for notification")
    nombre: str = Field(description="Given name or full contact name")
    telefono: str = Field(description="Telephone or mobile phone number")
    direccion: str | None = Field(default=None, description="Billing or shipping address")
    documento: str = Field(description="Identity document number")
    tipo_documento: DocumentType = Field(
        default=DocumentType.CI, description="Type of document (CI, RUC, PAS)"
    )
    razon_social: str = Field(description="Business or individual legal name")


class OrderItemModel(BaseModel):
    """Line item in a Pagopar order."""

    model_config = ConfigDict(extra="allow")

    id_producto: str = Field(description="Product SKU or identifier")
    nombre: str = Field(description="Product or service name")
    cantidad: int = Field(default=1, ge=1, description="Quantity")
    precio_total: float = Field(ge=0, description="Total price for this line item in PYG")
    categoria: str = Field(default="99", description="Pagopar category code")
    public_key: str | None = Field(default=None, description="Public key of the seller")


class CreateOrderRequest(BaseModel):
    """Request payload to initiate a Pagopar payment order."""

    model_config = ConfigDict(extra="allow")

    order_id: str = Field(description="Unique business order identifier in the caller system")
    monto_total: float = Field(gt=0, description="Total order amount in Guaraníes (PYG)")
    descripcion_resumen: str = Field(
        description="Summary description of purchase shown to customer"
    )
    fecha_maxima_pago: str | None = Field(
        default=None,
        description="Payment expiration timestamp formatted as 'YYYY-MM-DD HH:MM:SS'",
    )
    comprador: BuyerModel = Field(description="Buyer profile details")
    compras_items: list[OrderItemModel] = Field(min_length=1, description="Order line items")
    meta: dict[str, Any] | None = Field(default=None, description="Metadata dictionary")
    custom_data: dict[str, Any] | None = Field(
        default=None, description="Custom properties dictionary"
    )


class OrderResponse(BaseModel):
    """Details and checkout URL of a Pagopar payment order."""

    model_config = ConfigDict(extra="allow")

    order_id: str
    pagopar_hash: str | None = None
    checkout_url: str | None = None
    status: OrderStatus
    monto_total: float
    currency: str = "PYG"
    created_at: datetime
    updated_at: datetime | None = None
    paid_at: datetime | None = None
    payment_method: str | None = None
    receipt_number: str | None = None
    details: str | None = None
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class SyncOrderResponse(BaseModel):
    """Synchronization result from actively querying the upstream gateway."""

    model_config = ConfigDict(extra="allow")

    order_id: str
    pagopar_hash: str | None = None
    previous_status: OrderStatus
    current_status: OrderStatus
    synced: bool
    gateway_response: dict[str, Any] | None = None
    details: str | None = None
