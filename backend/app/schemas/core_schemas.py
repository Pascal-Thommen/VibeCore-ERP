"""Strict Pydantic v2 contracts for protected Core resources.

The REST boundary intentionally accepts only strings or integers for monetary
values.  JSON floating-point values are not accepted because financial amounts
must retain exact decimal semantics from the request through PostgreSQL.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AliasChoices,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


def _reject_float(value: Any) -> Any:
    """Reject IEEE-754 input before Pydantic converts it to ``Decimal``."""
    if isinstance(value, float):
        raise ValueError("financial values must be decimal strings or integers, never floats")
    return value


Money = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    Field(ge=Decimal("0"), max_digits=20, decimal_places=6),
]
PositiveMoney = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    Field(gt=Decimal("0"), max_digits=20, decimal_places=6),
]
Quantity = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    Field(gt=Decimal("0"), max_digits=20, decimal_places=6),
]
NonNegativeQuantity = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    Field(ge=Decimal("0"), max_digits=20, decimal_places=6),
]
ExchangeRate = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    Field(gt=Decimal("0"), max_digits=24, decimal_places=12),
]
TaxRate = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    Field(ge=Decimal("0"), le=Decimal("100"), max_digits=7, decimal_places=4),
]

Ruc = Annotated[str, StringConstraints(strict=True, pattern=r"^\d{5,8}$")]
VerificationDigit = Annotated[str, StringConstraints(strict=True, pattern=r"^\d$")]
CurrencyCode = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Z]{3}$")]
AccountCode = Annotated[
    str,
    StringConstraints(strict=True, max_length=32, pattern=r"^\d+(?:\.\d+)*$"),
]
TimbradoNumber = Annotated[str, StringConstraints(strict=True, pattern=r"^\d{8}$")]
EstablishmentCode = Annotated[str, StringConstraints(strict=True, pattern=r"^\d{3}$")]
PointOfIssueCode = Annotated[str, StringConstraints(strict=True, pattern=r"^\d{3}$")]
SifenDocumentType = Annotated[str, StringConstraints(strict=True, pattern=r"^\d{2}$")]
SifenEmissionType = Annotated[str, StringConstraints(strict=True, pattern=r"^\d$")]
SifenDocumentNumber = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^(?!0000000)\d{7}$"),
]
SifenSeries = Annotated[str, StringConstraints(strict=True, pattern=r"^(?:|[A-Z]{2})$")]
SifenCdc = Annotated[str, StringConstraints(strict=True, pattern=r"^\d{44}$")]
SifenSecurityCode = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^(?!000000000)\d{9}$"),
]

AccountType = Literal[
    "asset_current",
    "asset_fixed",
    "asset_non_current",
    "asset_prepayments",
    "asset_receivable",
    "equity",
    "equity_unaffected",
    "expense",
    "expense_depreciation",
    "income",
    "income_other",
    "liability_current",
    "liability_non_current",
    "liability_payable",
]
TaxScope = Literal["SALES", "PURCHASE", "BOTH"]
DocumentType = Literal["INVOICE", "CREDIT_NOTE", "DEBIT_NOTE", "RECEIPT", "REMITTANCE"]
DocumentDirection = Literal["SALES", "PURCHASE"]
DocumentStatus = Literal["DRAFT", "PENDING_APPROVAL", "POSTED", "CANCELLED", "REJECTED"]
SifenStatus = Literal["NOT_SENT", "PENDING", "ACCEPTED", "REJECTED", "CANCELLED"]


class CoreSchema(BaseModel):
    """Shared API behaviour and the JSONB extension field."""

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        populate_by_name=True,
        regex_engine="python-re",
        validate_assignment=True,
    )

    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )


class CoreReadSchema(CoreSchema):
    id: UUID
    created_at: datetime
    updated_at: datetime


class PartnerFields(CoreSchema):
    ruc: Ruc
    dv: VerificationDigit
    legal_name: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=250)]
    trade_name: Annotated[str | None, StringConstraints(strict=True, max_length=250)] = None
    is_customer: bool = False
    is_supplier: bool = False
    is_active: bool = True


class PartnerCreate(PartnerFields):
    pass


class PartnerUpdate(CoreSchema):
    ruc: Ruc | None = None
    dv: VerificationDigit | None = None
    legal_name: Annotated[
        str | None, StringConstraints(strict=True, min_length=1, max_length=250)
    ] = None
    trade_name: Annotated[str | None, StringConstraints(strict=True, max_length=250)] = None
    is_customer: bool | None = None
    is_supplier: bool | None = None
    is_active: bool | None = None


class PartnerRead(PartnerFields, CoreReadSchema):
    pass


class AccountFields(CoreSchema):
    code: AccountCode
    name: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=250)]
    account_type: AccountType
    parent_id: UUID | None = None
    reconcile: bool = False
    allow_posting: bool = True
    is_active: bool = True


class AccountCreate(AccountFields):
    pass


class AccountUpdate(CoreSchema):
    code: AccountCode | None = None
    name: Annotated[str | None, StringConstraints(strict=True, min_length=1, max_length=250)] = None
    account_type: AccountType | None = None
    parent_id: UUID | None = None
    reconcile: bool | None = None
    allow_posting: bool | None = None
    is_active: bool | None = None


class AccountRead(AccountFields, CoreReadSchema):
    pass


class TaxFields(CoreSchema):
    code: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=32)]
    name: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]
    rate: TaxRate
    scope: TaxScope = "BOTH"
    sales_account_id: UUID | None = None
    purchase_account_id: UUID | None = None
    is_active: bool = True

    @field_validator("rate")
    @classmethod
    def validate_paraguayan_iva_rate(cls, value: Decimal) -> Decimal:
        """The current Core supports the IVA rates present in the PY chart template."""
        if value not in {Decimal("0"), Decimal("5"), Decimal("10")}:
            raise ValueError("SIFEN IVA rate must be one of 0, 5, or 10")
        return value


class TaxCreate(TaxFields):
    pass


class TaxUpdate(CoreSchema):
    code: Annotated[str | None, StringConstraints(strict=True, min_length=1, max_length=32)] = None
    name: Annotated[str | None, StringConstraints(strict=True, min_length=1, max_length=100)] = None
    rate: TaxRate | None = None
    scope: TaxScope | None = None
    sales_account_id: UUID | None = None
    purchase_account_id: UUID | None = None
    is_active: bool | None = None

    @field_validator("rate")
    @classmethod
    def validate_paraguayan_iva_rate(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value not in {Decimal("0"), Decimal("5"), Decimal("10")}:
            raise ValueError("SIFEN IVA rate must be one of 0, 5, or 10")
        return value


class TaxRead(TaxFields, CoreReadSchema):
    pass


class ProductFields(CoreSchema):
    sku: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]
    name: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=250)]
    description: Annotated[str | None, StringConstraints(strict=True, max_length=10_000)] = None
    unit_of_measure: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=20)]
    is_stock_item: bool = True
    is_sales_item: bool = True
    is_purchase_item: bool = True
    standard_price: Money = Decimal("0")
    valuation_rate: Money = Decimal("0")
    weight_per_unit: NonNegativeQuantity | None = None
    weight_unit: Annotated[
        str | None, StringConstraints(strict=True, min_length=1, max_length=20)
    ] = None
    default_tax_id: UUID | None = None
    income_account_id: UUID | None = None
    expense_account_id: UUID | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_weight_unit(self) -> ProductFields:
        if self.weight_per_unit is not None and self.weight_unit is None:
            raise ValueError("weight_unit is required when weight_per_unit is set")
        return self


class ProductCreate(ProductFields):
    pass


class ProductUpdate(CoreSchema):
    sku: Annotated[str | None, StringConstraints(strict=True, min_length=1, max_length=100)] = None
    name: Annotated[str | None, StringConstraints(strict=True, min_length=1, max_length=250)] = None
    description: Annotated[str | None, StringConstraints(strict=True, max_length=10_000)] = None
    unit_of_measure: Annotated[
        str | None, StringConstraints(strict=True, min_length=1, max_length=20)
    ] = None
    is_stock_item: bool | None = None
    is_sales_item: bool | None = None
    is_purchase_item: bool | None = None
    standard_price: Money | None = None
    valuation_rate: Money | None = None
    weight_per_unit: NonNegativeQuantity | None = None
    weight_unit: Annotated[
        str | None, StringConstraints(strict=True, min_length=1, max_length=20)
    ] = None
    default_tax_id: UUID | None = None
    income_account_id: UUID | None = None
    expense_account_id: UUID | None = None
    is_active: bool | None = None


class ProductRead(ProductFields, CoreReadSchema):
    pass


class SifenIdentityFields(CoreSchema):
    """SIFEN identity fields stored as fiscal facts on a commercial document."""

    is_electronic: bool = False
    timbrado_number: TimbradoNumber | None = None
    establishment_code: EstablishmentCode | None = None
    point_of_issue_code: PointOfIssueCode | None = None
    sifen_document_type: SifenDocumentType | None = None
    sifen_emission_type: SifenEmissionType | None = None
    sifen_document_number: SifenDocumentNumber | None = None
    sifen_series: SifenSeries = ""
    sifen_cdc: SifenCdc | None = None
    sifen_security_code: SifenSecurityCode | None = None

    @model_validator(mode="after")
    def validate_sifen_identity(self) -> SifenIdentityFields:
        identity_values = {
            "timbrado_number": self.timbrado_number,
            "establishment_code": self.establishment_code,
            "point_of_issue_code": self.point_of_issue_code,
            "sifen_document_type": self.sifen_document_type,
            "sifen_emission_type": self.sifen_emission_type,
            "sifen_document_number": self.sifen_document_number,
            "sifen_cdc": self.sifen_cdc,
            "sifen_security_code": self.sifen_security_code,
        }
        present = [name for name, value in identity_values.items() if value is not None]

        if self.is_electronic:
            missing = [name for name, value in identity_values.items() if value is None]
            if missing:
                raise ValueError(
                    "electronic documents require a complete SIFEN identity: " + ", ".join(missing)
                )
            if int(self.sifen_security_code or "0") == int(self.sifen_document_number or "0"):
                raise ValueError("SIFEN security code must differ from the document number")
        elif present or self.sifen_series:
            raise ValueError("SIFEN identity fields are only allowed for electronic documents")

        return self


class DocumentItemCreate(CoreSchema):
    product_id: UUID | None = None
    tax_id: UUID
    product_code: Annotated[str | None, StringConstraints(strict=True, max_length=100)] = None
    description: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=500)]
    unit_of_measure: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=20)]
    quantity: Quantity
    unit_price: Money
    discount_amount: Money = Decimal("0")

    @model_validator(mode="after")
    def validate_discount(self) -> DocumentItemCreate:
        if self.discount_amount > self.quantity * self.unit_price:
            raise ValueError("discount_amount cannot exceed quantity multiplied by unit_price")
        return self


class DocumentItemUpdate(CoreSchema):
    product_id: UUID | None = None
    tax_id: UUID | None = None
    product_code: Annotated[str | None, StringConstraints(strict=True, max_length=100)] = None
    description: Annotated[
        str | None, StringConstraints(strict=True, min_length=1, max_length=500)
    ] = None
    unit_of_measure: Annotated[
        str | None, StringConstraints(strict=True, min_length=1, max_length=20)
    ] = None
    quantity: Quantity | None = None
    unit_price: Money | None = None
    discount_amount: Money | None = None


class DocumentItemRead(CoreReadSchema):
    document_id: UUID
    line_number: int
    product_id: UUID | None
    tax_id: UUID
    product_code: str | None
    description: str
    unit_of_measure: str
    quantity: Decimal
    unit_price: Decimal
    discount_amount: Decimal
    line_subtotal: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    line_total: Decimal
    functional_unit_price: Decimal
    functional_subtotal: Decimal
    functional_tax_amount: Decimal
    functional_total: Decimal


class DocumentCreate(SifenIdentityFields):
    document_type: DocumentType
    direction: DocumentDirection
    created_by_actor: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]
    partner_id: UUID
    associated_document_id: UUID | None = None
    issued_at: datetime
    due_date: date | None = None
    partner_reference: Annotated[str | None, StringConstraints(strict=True, max_length=100)] = None
    currency_code: CurrencyCode
    functional_currency_code: Literal["PYG"] = "PYG"
    exchange_rate: ExchangeRate = Decimal("1")
    issuer_ruc: Ruc
    issuer_dv: VerificationDigit
    issuer_legal_name: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=250)]
    items: list[DocumentItemCreate] = Field(min_length=1)

    @field_validator("issued_at")
    @classmethod
    def require_timezone_aware_issued_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("issued_at must include a timezone offset")
        return value

    @model_validator(mode="after")
    def validate_currency_and_line_count(self) -> DocumentCreate:
        if self.currency_code == "PYG" and self.exchange_rate != Decimal("1"):
            raise ValueError("PYG documents must use an exchange_rate of exactly 1")
        return self


class DocumentUpdate(CoreSchema):
    """Only mutable DRAFT header fields; fiscal identity and totals are immutable snapshots."""

    partner_id: UUID | None = None
    due_date: date | None = None
    partner_reference: Annotated[str | None, StringConstraints(strict=True, max_length=100)] = None


class DocumentRead(CoreReadSchema):
    document_type: DocumentType
    direction: DocumentDirection
    status: DocumentStatus
    created_by_actor: str
    partner_id: UUID
    associated_document_id: UUID | None
    issued_at: datetime
    due_date: date | None
    partner_reference: str | None
    currency_code: CurrencyCode
    functional_currency_code: CurrencyCode
    exchange_rate: Decimal
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    functional_subtotal: Decimal
    functional_tax_total: Decimal
    functional_total: Decimal
    total_quantity: Decimal
    issuer_ruc: Ruc
    issuer_dv: VerificationDigit
    issuer_legal_name: str
    partner_ruc: Ruc
    partner_dv: VerificationDigit
    partner_legal_name: str
    is_electronic: bool
    timbrado_number: TimbradoNumber | None
    establishment_code: EstablishmentCode | None
    point_of_issue_code: PointOfIssueCode | None
    sifen_document_type: SifenDocumentType | None
    sifen_emission_type: SifenEmissionType | None
    sifen_document_number: SifenDocumentNumber | None
    sifen_series: SifenSeries
    sifen_cdc: SifenCdc | None
    sifen_security_code: SifenSecurityCode | None
    sifen_status: SifenStatus
    sifen_result: dict[str, Any]
    items: list[DocumentItemRead]
