"""Pydantic schemas for Bancard Adapter requests and responses."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from bancard.constants import CURRENCY_PYG, TransactionStatus


class SingleBuyInitRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    amount: Decimal = Field(..., gt=Decimal("0"), description="Transaction amount (e.g. 45000.00)")
    currency: str = Field(default=CURRENCY_PYG, pattern="^(PYG|USD)$", description="ISO 4217 currency")
    description: str = Field(..., min_length=1, max_length=255, description="Item or order description")
    user_id: Optional[str] = Field(None, description="Client or user identifier")
    return_url: Optional[str] = Field(None, description="Frontend success redirect URL")
    cancel_url: Optional[str] = Field(None, description="Frontend cancel redirect URL")
    idempotency_key: Optional[str] = Field(None, max_length=128, description="Unique client idempotency key")
    meta: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadata dictionary")
    custom_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom application attributes")


class SingleBuyInitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shop_process_id: int
    process_id: str
    token: str
    status: str
    amount: Decimal
    currency: str
    checkout_url: str
    script_url: str


class CardCatastroRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: str = Field(..., min_length=1, description="Unique user or customer identifier")
    card_id: int = Field(..., gt=0, description="Sequential card slot index for user")
    user_cell_phone: Optional[str] = Field(None, description="Cardholder phone number")
    user_mail: Optional[str] = Field(None, description="Cardholder email address")
    return_url: Optional[str] = Field(None, description="Redirect URL upon completion")
    meta: Optional[Dict[str, Any]] = Field(default_factory=dict)
    custom_data: Optional[Dict[str, Any]] = Field(default_factory=dict)


class CardCatastroResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    process_id: str
    status: str
    user_id: str
    card_id: int


class TokenChargeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    alias_token: str = Field(..., min_length=1, description="Stored card token from catastro")
    amount: Decimal = Field(..., gt=Decimal("0"), description="Charge amount")
    currency: str = Field(default=CURRENCY_PYG, pattern="^(PYG|USD)$")
    description: str = Field(..., min_length=1, max_length=255)
    user_id: str = Field(..., min_length=1)
    idempotency_key: Optional[str] = Field(None, max_length=128)
    meta: Optional[Dict[str, Any]] = Field(default_factory=dict)
    custom_data: Optional[Dict[str, Any]] = Field(default_factory=dict)


class TokenChargeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shop_process_id: int
    status: str
    response_code: str
    response_description: str
    ticket_number: Optional[str] = None
    authorization_number: Optional[str] = None


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reason: Optional[str] = Field(default="Customer cancellation or timeout", max_length=255)


class RollbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shop_process_id: int
    status: str
    response_code: str
    response_description: str


class CatastroQrGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    amount: Decimal = Field(..., gt=Decimal("0"), description="Amount in PYG")
    currency: str = Field(default=CURRENCY_PYG, pattern="^(PYG)$")
    description: str = Field(..., min_length=1, max_length=255)
    user_id: Optional[str] = Field(None, description="Purchasing user ID")
    idempotency_key: Optional[str] = Field(None, max_length=128)
    expires_in_minutes: int = Field(default=15, ge=1, le=1440)
    meta: Optional[Dict[str, Any]] = Field(default_factory=dict)
    custom_data: Optional[Dict[str, Any]] = Field(default_factory=dict)


class CatastroQrGenerateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shop_process_id: int
    qr_payload: str
    qr_image_data_uri: str
    status: str
    amount: Decimal
    currency: str
    expires_at: datetime


class CatastroQrStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shop_process_id: int
    status: str
    amount: Decimal
    currency: str
    payment_method: str
    ticket_number: Optional[str] = None
    authorization_number: Optional[str] = None
    updated_at: datetime


class BancardWebhookOperation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token: str
    shop_process_id: int
    amount: str
    currency: str
    response: Optional[str] = None
    response_code: str
    response_description: Optional[str] = None
    extended_response_description: Optional[str] = None
    ticket_number: Optional[str] = None
    authorization_number: Optional[str] = None
    security_information: Optional[Dict[str, Any]] = None


class BancardWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    operation: BancardWebhookOperation


class BancardWebhookResponse(BaseModel):
    status: str
    shop_process_id: int
    transaction_status: str
    message: str


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    previous_status: Optional[str] = None
    new_status: str
    reason: Optional[str] = None
    actor: str
    created_at: datetime


class TransactionDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    shop_process_id: int
    idempotency_key: Optional[str] = None
    user_id: Optional[str] = None
    amount: Decimal
    currency: str
    payment_method: str
    status: str
    description: Optional[str] = None
    response_code: Optional[str] = None
    response_description: Optional[str] = None
    ticket_number: Optional[str] = None
    authorization_number: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    audit_logs: List[AuditLogEntry] = Field(default_factory=list)


class DeadLetterItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    target_url: str
    event_type: str
    payload: str
    attempts: int
    last_attempt_at: Optional[datetime] = None
    error_message: Optional[str] = None
    status: str
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    database: str
    environment: str
    pending_transactions_count: int
    dead_letter_count: int
