"""Pydantic schemas and data models for Stripe Payment Gateway Adapter."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OrderStatus(StrEnum):
    INITIATED = "INITIATED"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class LineItemModel(BaseModel):
    """Line item for Stripe Checkout Session."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(description="Product or service name")
    amount: float = Field(ge=0, description="Price per unit in human decimal currency")
    quantity: int = Field(default=1, ge=1, description="Quantity")
    currency: str | None = Field(default=None, description="Currency ISO code")
    description: str | None = Field(default=None, description="Detailed item description")


class CreateCheckoutSessionRequest(BaseModel):
    """Payload to create a Stripe Checkout Session."""

    model_config = ConfigDict(extra="allow")

    order_id: str = Field(description="Unique business order identifier in VibeCore ERP")
    amount_total: float = Field(gt=0, description="Total order amount in human decimal units")
    currency: str = Field(default="USD", description="Currency ISO 4217 code (e.g. USD, EUR, PYG)")
    description: str = Field(description="Summary description of purchase shown to customer")
    customer_email: str = Field(description="Customer email address for notifications and receipt")
    success_url: str | None = Field(
        default=None, description="Redirect URL after successful payment"
    )
    cancel_url: str | None = Field(default=None, description="Redirect URL if customer cancels")
    items: list[LineItemModel] | None = Field(
        default=None, description="Optional itemized line items"
    )
    meta: dict[str, Any] | None = Field(default=None, description="Metadata dictionary")
    custom_data: dict[str, Any] | None = Field(
        default=None, description="Custom properties dictionary"
    )


class CreatePaymentIntentRequest(BaseModel):
    """Payload to create a direct Stripe PaymentIntent."""

    model_config = ConfigDict(extra="allow")

    order_id: str = Field(description="Unique business order identifier in VibeCore ERP")
    amount: float = Field(gt=0, description="Payment amount in human decimal units")
    currency: str = Field(default="USD", description="Currency ISO 4217 code (e.g. USD, EUR, PYG)")
    description: str = Field(description="Payment description")
    customer_email: str | None = Field(default=None, description="Customer email address")
    payment_method: str | None = Field(
        default=None, description="Optional Stripe payment method ID"
    )
    confirm: bool = Field(
        default=False, description="Whether to confirm immediately if payment_method provided"
    )
    meta: dict[str, Any] | None = Field(default=None, description="Metadata dictionary")
    custom_data: dict[str, Any] | None = Field(
        default=None, description="Custom properties dictionary"
    )


class PaymentResponse(BaseModel):
    """Response returned for Stripe Checkout Sessions and PaymentIntents."""

    model_config = ConfigDict(extra="allow")

    order_id: str
    stripe_id: str
    payment_type: str = Field(description="'checkout_session' or 'payment_intent'")
    checkout_url: str | None = None
    client_secret: str | None = None
    status: OrderStatus
    amount: float
    amount_cents: int
    currency: str
    customer_email: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    paid_at: datetime | None = None
    payment_method: str | None = None
    receipt_url: str | None = None
    details: str | None = None
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class SyncPaymentResponse(BaseModel):
    """Result of actively polling and synchronizing payment status with Stripe."""

    model_config = ConfigDict(extra="allow")

    order_id: str
    stripe_id: str
    previous_status: OrderStatus
    current_status: OrderStatus
    synced: bool
    gateway_response: dict[str, Any] | None = None
    details: str | None = None
