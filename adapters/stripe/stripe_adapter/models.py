"""
Pydantic v2 schemas and data transfer objects for Stripe Adapter.
Harmonized with VibeCore ERP Multi-Gateway Payment Standards.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrderStatus(str, Enum):
    INITIATED = "INITIATED"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Currencies with 0 decimal places according to ISO 4217 and Stripe documentation
ZERO_DECIMAL_CURRENCIES: Set[str] = {
    "BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW",
    "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF",
}

# Currencies with 3 decimal places
THREE_DECIMAL_CURRENCIES: Set[str] = {
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
    currency: Optional[str] = Field(default=None, description="Currency ISO code")
    description: Optional[str] = Field(default=None, description="Detailed item description")


class CreateCheckoutSessionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order_id: str = Field(description="Unique business order identifier in VibeCore ERP")
    amount_total: float = Field(gt=0, description="Total order amount in human decimal units")
    currency: str = Field(default="USD", description="Currency ISO 4217 code (e.g. USD, EUR, PYG)")
    description: str = Field(description="Summary description of purchase shown to customer")
    customer_email: str = Field(description="Customer email address for notifications and receipt")
    success_url: Optional[str] = Field(default=None, description="Redirect URL after successful payment")
    cancel_url: Optional[str] = Field(default=None, description="Redirect URL if customer cancels")
    items: Optional[List[LineItemModel]] = Field(default=None, description="Optional itemized line items")
    meta: Optional[Dict[str, Any]] = Field(default=None, description="Metadata dictionary")
    custom_data: Optional[Dict[str, Any]] = Field(default=None, description="Custom properties dictionary")

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
    customer_email: Optional[str] = Field(default=None, description="Customer email address")
    payment_method: Optional[str] = Field(default=None, description="Optional specific Stripe payment method ID")
    confirm: bool = Field(default=False, description="Whether to confirm immediately if payment_method provided")
    meta: Optional[Dict[str, Any]] = Field(default=None, description="Metadata dictionary")
    custom_data: Optional[Dict[str, Any]] = Field(default=None, description="Custom properties dictionary")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        return v.strip().upper()


class PaymentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order_id: str
    stripe_id: str
    payment_type: str = Field(description="'checkout_session' or 'payment_intent'")
    checkout_url: Optional[str] = None
    client_secret: Optional[str] = None
    status: OrderStatus
    amount: float
    amount_cents: int
    currency: str
    customer_email: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    payment_method: Optional[str] = None
    receipt_url: Optional[str] = None
    details: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
    custom_data: Optional[Dict[str, Any]] = None


class HarmonizedCoreEvent(BaseModel):
    """Event schema published for VibeCore Finance Core consumption."""
    model_config = ConfigDict(extra="ignore")

    event: str = Field(description="'payment.succeeded' or 'payment.failed'")
    gateway: str = "stripe"
    order_id: str
    payment_id: str
    session_id: Optional[str] = None
    amount: float
    currency: str
    amount_in_cents: int
    status: str
    paid_at: Optional[str] = None
    payment_method: Optional[str] = None
    receipt_url: Optional[str] = None
    failure_reason: Optional[str] = None
    customer_email: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
    custom_data: Optional[Dict[str, Any]] = None


class SyncPaymentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order_id: str
    stripe_id: str
    previous_status: OrderStatus
    current_status: OrderStatus
    synced: bool
    gateway_response: Optional[Dict[str, Any]] = None
    details: Optional[str] = None


class WebhookProcessResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str
    event_id: str
    event_type: str
    order_id: Optional[str] = None
    payment_id: Optional[str] = None
    processed: bool
    details: Optional[str] = None
