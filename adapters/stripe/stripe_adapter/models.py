"""
Pydantic v2 schemas and data transfer objects for Stripe Adapter.
Harmonized with VibeCore ERP Multi-Gateway Payment Standards.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrderStatus(str, Enum):
    INITIATED = "INITIATED"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Currencies with 0 decimal places according to ISO 4217 and Stripe documentation
ZERO_DECIMAL_CURRENCIES: set[str] = {
    "BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW",
    "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF",
}

# Currencies with 3 decimal places
THREE_DECIMAL_CURRENCIES: set[str] = {
    "BHD", "JOD", "KWD", "OMR", "TND",
}


class CurrencyHelper:
    """Utility to convert amounts between human decimal currency units and Stripe smallest integer units (cents)."""

    @classmethod
    def get_decimal_multiplier(cls, currency: str) -> int:
        cur = currency.upper().strip()
        if cur in ZERO_DECIMAL_CURRENCIES:
            return 1
        if cur in THREE_DECIMAL_CURRENCIES:
            return 1000
        return 100

    @classmethod
    def amount_to_cents(cls, amount: float, currency: str) -> int:
        multiplier = cls.get_decimal_multiplier(currency)
        return int(round(amount * multiplier))

    @classmethod
    def cents_to_amount(cls, cents: int, currency: str) -> float:
        multiplier = cls.get_decimal_multiplier(currency)
        return float(cents) / float(multiplier)


class LineItemModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(description="Product or service name")
    amount: float = Field(ge=0, description="Price per unit in human decimal currency")
    quantity: int = Field(default=1, ge=1, description="Quantity")
    currency: str | None = Field(default=None, description="Currency ISO code")
    description: str | None = Field(default=None, description="Detailed item description")


class CreateCheckoutSessionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order_id: str = Field(description="Unique business order identifier in VibeCore ERP")
    amount_total: float = Field(gt=0, description="Total order amount in human decimal units")
    currency: str = Field(default="USD", description="Currency ISO 4217 code (e.g. USD, EUR, PYG)")
    description: str = Field(description="Summary description of purchase shown to customer")
    customer_email: str = Field(description="Customer email address for notifications and receipt")
    success_url: str | None = Field(default=None, description="Redirect URL after successful payment")
    cancel_url: str | None = Field(default=None, description="Redirect URL if customer cancels")
    items: list[LineItemModel] | None = Field(default=None, description="Optional itemized line items")
    meta: dict[str, Any] | None = Field(default=None, description="Metadata dictionary")
    custom_data: dict[str, Any] | None = Field(default=None, description="Custom properties dictionary")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("customer_email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError(f"Invalid email address: {v}")
        return v


class CreatePaymentIntentRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order_id: str = Field(description="Unique business order identifier in VibeCore ERP")
    amount: float = Field(gt=0, description="Payment amount in human decimal units")
    currency: str = Field(default="USD", description="Currency ISO 4217 code (e.g. USD, EUR, PYG)")
    description: str = Field(description="Payment description")
    customer_email: str | None = Field(default=None, description="Customer email address")
    payment_method: str | None = Field(default=None, description="Optional specific Stripe payment method ID")
    confirm: bool = Field(default=False, description="Whether to confirm immediately if payment_method provided")
    meta: dict[str, Any] | None = Field(default=None, description="Metadata dictionary")
    custom_data: dict[str, Any] | None = Field(default=None, description="Custom properties dictionary")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        return v.strip().upper()


class PaymentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

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


class HarmonizedCoreEvent(BaseModel):
    """Event schema published for VibeCore Finance Core consumption."""
    model_config = ConfigDict(extra="ignore")

    event: str = Field(description="'payment.succeeded' or 'payment.failed'")
    gateway: str = "stripe"
    order_id: str
    payment_id: str
    session_id: str | None = None
    amount: float
    currency: str
    amount_in_cents: int
    status: str
    paid_at: str | None = None
    payment_method: str | None = None
    receipt_url: str | None = None
    failure_reason: str | None = None
    customer_email: str | None = None
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class SyncPaymentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order_id: str
    stripe_id: str
    previous_status: OrderStatus
    current_status: OrderStatus
    synced: bool
    gateway_response: dict[str, Any] | None = None
    details: str | None = None


class WebhookProcessResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str
    event_id: str
    event_type: str
    order_id: str | None = None
    payment_id: str | None = None
    processed: bool
    details: str | None = None
