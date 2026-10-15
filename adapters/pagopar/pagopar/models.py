"""
Pydantic v2 schemas and data transfer objects for Pagopar Adapter.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentType(str, Enum):
    CI = "CI"
    RUC = "RUC"
    PAS = "PAS"


class OrderStatus(str, Enum):
    INITIATED = "INITIATED"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BuyerModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ruc: str = Field(description="Tax identification or identification number")
    email: str = Field(description="Buyer email address for notification")
    nombre: str = Field(description="Given name or full contact name")
    telefono: str = Field(description="Telephone or mobile phone number")
    direccion: Optional[str] = Field(default=None, description="Billing or shipping address")
    documento: str = Field(description="Identity document number")
    tipo_documento: DocumentType = Field(default=DocumentType.CI, description="Type of document (CI, RUC, PAS)")
    razon_social: str = Field(description="Business or individual legal name")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        v = v.strip()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError(f"Invalid email address: {v}")
        return v


class OrderItemModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id_producto: str = Field(description="Product SKU or identifier")
    nombre: str = Field(description="Product or service name")
    cantidad: int = Field(default=1, ge=1, description="Quantity")
    precio_total: float = Field(ge=0, description="Total price for this line item in PYG")
    categoria: str = Field(default="99", description="Pagopar category code")
    public_key: Optional[str] = Field(default=None, description="Public key of the seller")


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order_id: str = Field(description="Unique business order identifier in the caller system")
    monto_total: float = Field(gt=0, description="Total order amount in Guaraníes (PYG)")
    descripcion_resumen: str = Field(description="Summary description of purchase shown to customer")
    fecha_maxima_pago: Optional[str] = Field(
        default=None,
        description="Payment expiration timestamp formatted as 'YYYY-MM-DD HH:MM:SS'",
    )
    comprador: BuyerModel = Field(description="Buyer profile details")
    compras_items: List[OrderItemModel] = Field(min_length=1, description="Order line items")
    meta: Optional[Dict[str, Any]] = Field(default=None, description="Metadata dictionary")
    custom_data: Optional[Dict[str, Any]] = Field(default=None, description="Custom properties dictionary")


class OrderResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order_id: str
    pagopar_hash: Optional[str] = None
    checkout_url: Optional[str] = None
    status: OrderStatus
    monto_total: float
    currency: str = "PYG"
    created_at: datetime
    updated_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    payment_method: Optional[str] = None
    receipt_number: Optional[str] = None
    details: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
    custom_data: Optional[Dict[str, Any]] = None


class PagoparWebhookItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pagado: bool = Field(description="Payment status boolean")
    fecha_pago: Optional[str] = Field(default=None, description="Payment date timestamp")
    forma_pago: Optional[str] = Field(default=None, description="Payment method description")
    forma_pago_identificador: Optional[str] = Field(default=None, description="Payment method ID")
    hash_pedido: str = Field(description="Unique 64-character Pagopar transaction hash")
    monto: Union[float, int, str] = Field(description="Paid amount")
    token: str = Field(description="SHA-1 signature token sent by Pagopar")
    numero_comprobante: Optional[str] = Field(default=None, description="Receipt or transaction number")
    comentario: Optional[str] = Field(default=None, description="Optional payment comment")
    identificador_pago: Optional[int] = Field(default=None, description="Payment identification integer")


class PagoparWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    respuesta: bool = Field(description="Response status indicator")
    resultado: List[PagoparWebhookItem] = Field(description="Array of payment notifications")


class WebhookProcessResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str
    processed_count: int
    items: List[Dict[str, Any]] = Field(default_factory=list)


class SyncOrderResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order_id: str
    pagopar_hash: Optional[str] = None
    previous_status: OrderStatus
    current_status: OrderStatus
    synced: bool
    gateway_response: Optional[Dict[str, Any]] = None
    details: Optional[str] = None
