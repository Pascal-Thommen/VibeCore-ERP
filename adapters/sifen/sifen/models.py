"""
Domain models and schemas for SIFEN Dynamic DTE resolution, XML generation, and Outbox Queue.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from sifen.constants import (
    DTE_BOLETA_RESIMPLE,
    DTE_FACTURA_ELECTRONICA,
    DTE_TYPE_CODES,
    DTE_TYPE_DESCRIPTIONS,
    TaxRegime,
)

Ruc = Annotated[str, StringConstraints(strict=True, pattern=r"^\d{5,8}$")]
VerificationDigit = Annotated[str, StringConstraints(strict=True, pattern=r"^\d$")]


class OutboxStatus(StrEnum):
    QUEUED = "QUEUED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class MandantObligacion(BaseModel):
    """A registered tax obligation on the taxpayer's RUC profile."""

    model_config = ConfigDict(extra="ignore")

    code: int
    description: str = ""


class MandantRucProfile(BaseModel):
    """The fiscal profile of the tenant/mandant issuing electronic documents."""

    model_config = ConfigDict(extra="ignore")

    ruc: Ruc
    dv: VerificationDigit
    legal_name: str
    trade_name: str | None = None
    obligaciones: list[int | MandantObligacion]
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class ResolvedProfile(BaseModel):
    """The resolved DTE behavior derived from the Mandant's RUC profile."""

    model_config = ConfigDict(extra="forbid")

    regime: TaxRegime
    obligation_code: int
    dte_type: int
    dte_type_code: str
    dte_type_description: str
    iva_applicable: bool
    requires_iva_breakdown: bool

    @classmethod
    def from_regime(cls, regime: TaxRegime, obligation_code: int) -> "ResolvedProfile":
        if regime in (TaxRegime.IRE_GENERAL, TaxRegime.IRE_SIMPLE):
            dte_type = DTE_FACTURA_ELECTRONICA
            iva_applicable = True
            requires_iva_breakdown = True
        elif regime == TaxRegime.IRE_RESIMPLE:
            dte_type = DTE_BOLETA_RESIMPLE
            iva_applicable = False
            requires_iva_breakdown = False
        else:
            raise ValueError(f"Unsupported regime: {regime}")

        return cls(
            regime=regime,
            obligation_code=obligation_code,
            dte_type=dte_type,
            dte_type_code=DTE_TYPE_CODES[dte_type],
            dte_type_description=DTE_TYPE_DESCRIPTIONS[dte_type],
            iva_applicable=iva_applicable,
            requires_iva_breakdown=requires_iva_breakdown,
        )


class ItemTaxDetail(BaseModel):
    """Calculated tax values for a single item line."""

    model_config = ConfigDict(extra="forbid")

    afectacion_iva: int
    des_afectacion_iva: str
    proporcion_iva: Decimal
    tasa_iva: Decimal
    base_gravada: Decimal
    liquidacion_iva: Decimal
    total_item: Decimal


class DteItemInput(BaseModel):
    """Input line item for SIFEN DTE generation."""

    model_config = ConfigDict(extra="forbid")

    line_number: int = Field(gt=0)
    code: str = ""
    description: str = Field(min_length=1)
    unit_of_measure: str = "77"
    quantity: Decimal = Field(gt=Decimal(0))
    unit_price: Decimal = Field(ge=Decimal(0))
    discount: Decimal = Field(default=Decimal(0), ge=Decimal(0))
    tax_rate: Decimal = Field(default=Decimal(10), ge=Decimal(0), le=Decimal(100))


class DteHeaderInput(BaseModel):
    """Input header data for SIFEN DTE generation."""

    model_config = ConfigDict(extra="forbid")

    timbrado_number: str = Field(pattern=r"^\d{8}$")
    establishment_code: str = Field(default="001", pattern=r"^\d{3}$")
    point_of_issue_code: str = Field(default="001", pattern=r"^\d{3}$")
    document_number: str = Field(pattern=r"^\d{7}$")
    issue_date: datetime
    security_code: str = Field(pattern=r"^\d{9}$")
    emission_type: int = Field(default=1, ge=1, le=2)
    contributor_type: int = Field(
        default=2, ge=1, le=2
    )  # 1=Persona Fisica, 2=Persona Juridica
    issuer_ruc: Ruc
    issuer_dv: VerificationDigit
    issuer_legal_name: str
    issuer_trade_name: str | None = None
    issuer_address: str = "Asuncion, Paraguay"
    issuer_city: str = "Asuncion"
    issuer_department_code: str = "1"
    issuer_district_code: str = "1"
    issuer_city_code: str = "1"
    issuer_economic_activity_code: str = "62010"
    issuer_economic_activity_desc: str = "Actividades de programacion informatica"
    receiver_ruc: str | None = None
    receiver_dv: str | None = None
    receiver_doc_number: str | None = None
    receiver_doc_type: int | None = None
    receiver_legal_name: str = "Consumidor Final"
    receiver_nature: int = 1  # 1=Contribuyente, 2=No Contribuyente
    operation_type: int = 1  # 1=B2B, 2=B2C, 3=B2G, 4=B2F
    currency: str = "PYG"
    exchange_rate: Decimal = Decimal(1)


class GenerateXmlRequest(BaseModel):
    """Request payload for generating SIFEN DTE XML."""

    model_config = ConfigDict(extra="ignore")

    header: DteHeaderInput
    items: list[DteItemInput] = Field(min_length=1)
    profile: MandantRucProfile
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class SubmitDteRequest(BaseModel):
    """Request payload for generating and transmitting a SIFEN DTE with persistent outbox fallback."""

    model_config = ConfigDict(extra="ignore")

    header: DteHeaderInput
    items: list[DteItemInput] = Field(min_length=1)
    profile: MandantRucProfile
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class DteOutboxResponse(BaseModel):
    """Response representing a DTE submission or outbox entry."""

    model_config = ConfigDict(extra="ignore")

    cdc: str
    dte_type: int
    issuer_ruc: str
    document_number: str
    total_amount: Decimal
    currency: str
    status: OutboxStatus
    sifen_code: str | None = None
    sifen_message: str | None = None
    protocol_number: str | None = None
    retry_count: int
    last_error: str | None = None
    xml_payload: str
    created_at: datetime
    updated_at: datetime
    transmitted_at: datetime | None = None
    meta: dict[str, Any] | None = None
    custom_data: dict[str, Any] | None = None


class OutboxFlushResponse(BaseModel):
    """Result of flushing queued DTEs from the persistent outbox."""

    model_config = ConfigDict(extra="ignore")

    processed_count: int
    accepted_count: int
    rejected_count: int
    still_queued_count: int
    items: list[DteOutboxResponse] = Field(default_factory=list)
