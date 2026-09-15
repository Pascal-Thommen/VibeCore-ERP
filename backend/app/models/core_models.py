"""Canonical financial master and commercial-document models in the ``core`` schema.

The ``metadata`` database column deliberately uses the ``metadata_`` Python
attribute.  SQLAlchemy reserves ``metadata`` on declarative model classes for
the shared :class:`~sqlalchemy.schema.MetaData` collection.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.financial_types import (
    EXCHANGE_RATE_NUMERIC,
    MONEY_NUMERIC,
    QUANTITY_NUMERIC,
    TAX_RATE_NUMERIC,
)
from app.db.base import Base, CORE_SCHEMA


class CoreModelMixin:
    """Columns shared by durable entities in the protected Core schema."""

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Partner(CoreModelMixin, Base):
    """Canonical fiscal identity for customers and suppliers."""

    __tablename__ = "partner"
    __table_args__ = (
        CheckConstraint("ruc ~ '^[0-9]{5,8}$'", name="ruc_format"),
        CheckConstraint("dv ~ '^[0-9]$'", name="dv_format"),
        UniqueConstraint("ruc", "dv", name="ruc_dv"),
        {"schema": CORE_SCHEMA},
    )

    ruc: Mapped[str] = mapped_column(String(8), nullable=False)
    dv: Mapped[str] = mapped_column(String(1), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(250), nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(250))
    is_customer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_supplier: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    documents: Mapped[list[Document]] = relationship(back_populates="partner")


class Account(CoreModelMixin, Base):
    """A node in the Paraguayan chart of accounts."""

    __tablename__ = "account"
    __table_args__ = (
        CheckConstraint("code ~ '^[0-9]+(\\.[0-9]+)*$'", name="code_format"),
        CheckConstraint(
            "account_type IN ("
            "'asset_current', 'asset_fixed', 'asset_non_current', 'asset_prepayments', "
            "'asset_receivable', 'equity', 'equity_unaffected', 'expense', "
            "'expense_depreciation', 'income', 'income_other', 'liability_current', "
            "'liability_non_current', 'liability_payable'"
            ")",
            name="account_type",
        ),
        UniqueConstraint("code", name="code"),
        {"schema": CORE_SCHEMA},
    )

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    account_type: Mapped[str] = mapped_column(String(40), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{CORE_SCHEMA}.account.id", ondelete="RESTRICT")
    )
    reconcile: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    allow_posting: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    parent: Mapped[Account | None] = relationship(
        back_populates="children", remote_side="Account.id"
    )
    children: Mapped[list[Account]] = relationship(back_populates="parent")


class Tax(CoreModelMixin, Base):
    """IVA definition, including the associated purchase and sales accounts."""

    __tablename__ = "tax"
    __table_args__ = (
        CheckConstraint("rate >= 0 AND rate <= 100", name="rate_range"),
        CheckConstraint("scope IN ('SALES', 'PURCHASE', 'BOTH')", name="scope"),
        UniqueConstraint("code", name="code"),
        {"schema": CORE_SCHEMA},
    )

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rate: Mapped[Decimal] = mapped_column(TAX_RATE_NUMERIC, nullable=False)
    scope: Mapped[str] = mapped_column(String(12), nullable=False, server_default=text("'BOTH'"))
    sales_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{CORE_SCHEMA}.account.id", ondelete="RESTRICT")
    )
    purchase_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{CORE_SCHEMA}.account.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    sales_account: Mapped[Account | None] = relationship(foreign_keys=[sales_account_id])
    purchase_account: Mapped[Account | None] = relationship(foreign_keys=[purchase_account_id])


class Product(CoreModelMixin, Base):
    """Product or service master data usable in purchase and sales documents."""

    __tablename__ = "product"
    __table_args__ = (
        CheckConstraint("standard_price >= 0", name="standard_price_nonnegative"),
        CheckConstraint("valuation_rate >= 0", name="valuation_rate_nonnegative"),
        CheckConstraint(
            "weight_per_unit IS NULL OR weight_per_unit >= 0", name="weight_nonnegative"
        ),
        UniqueConstraint("sku", name="sku"),
        {"schema": CORE_SCHEMA},
    )

    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    unit_of_measure: Mapped[str] = mapped_column(String(20), nullable=False)
    is_stock_item: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    is_sales_item: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    is_purchase_item: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    standard_price: Mapped[Decimal] = mapped_column(
        MONEY_NUMERIC, nullable=False, server_default=text("0")
    )
    valuation_rate: Mapped[Decimal] = mapped_column(
        MONEY_NUMERIC, nullable=False, server_default=text("0")
    )
    weight_per_unit: Mapped[Decimal | None] = mapped_column(QUANTITY_NUMERIC)
    weight_unit: Mapped[str | None] = mapped_column(String(20))
    default_tax_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{CORE_SCHEMA}.tax.id", ondelete="RESTRICT")
    )
    income_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{CORE_SCHEMA}.account.id", ondelete="RESTRICT")
    )
    expense_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{CORE_SCHEMA}.account.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    default_tax: Mapped[Tax | None] = relationship(foreign_keys=[default_tax_id])
    income_account: Mapped[Account | None] = relationship(foreign_keys=[income_account_id])
    expense_account: Mapped[Account | None] = relationship(foreign_keys=[expense_account_id])


class Document(CoreModelMixin, Base):
    """Commercial document header with fiscal and SIFEN traceability facts."""

    __tablename__ = "document"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('INVOICE', 'CREDIT_NOTE', 'DEBIT_NOTE', 'RECEIPT', 'REMITTANCE')",
            name="document_type",
        ),
        CheckConstraint("direction IN ('SALES', 'PURCHASE')", name="direction"),
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_APPROVAL', 'POSTED', 'CANCELLED', 'REJECTED')",
            name="status",
        ),
        CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="currency_code_format"),
        CheckConstraint(
            "functional_currency_code ~ '^[A-Z]{3}$'",
            name="functional_currency_code_format",
        ),
        CheckConstraint("exchange_rate > 0", name="exchange_rate_positive"),
        CheckConstraint(
            "subtotal >= 0 AND tax_total >= 0 AND total >= 0", name="amounts_nonnegative"
        ),
        CheckConstraint(
            "functional_subtotal >= 0 AND functional_tax_total >= 0 AND functional_total >= 0",
            name="functional_amounts_nonnegative",
        ),
        CheckConstraint("total_quantity >= 0", name="total_quantity_nonnegative"),
        CheckConstraint("issuer_ruc ~ '^[0-9]{5,8}$'", name="issuer_ruc_format"),
        CheckConstraint("issuer_dv ~ '^[0-9]$'", name="issuer_dv_format"),
        CheckConstraint("partner_ruc ~ '^[0-9]{5,8}$'", name="partner_ruc_format"),
        CheckConstraint("partner_dv ~ '^[0-9]$'", name="partner_dv_format"),
        CheckConstraint(
            "(timbrado_number IS NULL OR timbrado_number ~ '^[0-9]{8}$') AND "
            "(establishment_code IS NULL OR establishment_code ~ '^[0-9]{3}$') AND "
            "(point_of_issue_code IS NULL OR point_of_issue_code ~ '^[0-9]{3}$') AND "
            "(sifen_document_type IS NULL OR sifen_document_type ~ '^[0-9]{2}$') AND "
            "(sifen_emission_type IS NULL OR sifen_emission_type ~ '^[0-9]$') AND "
            "(sifen_document_number IS NULL OR sifen_document_number ~ '^[0-9]{7}$') AND "
            "(sifen_cdc IS NULL OR sifen_cdc ~ '^[0-9]{44}$') AND "
            "(sifen_security_code IS NULL OR sifen_security_code ~ '^[0-9]{9}$') AND "
            "sifen_series ~ '^$|^[A-Z]{2}$'",
            name="sifen_identity_format",
        ),
        CheckConstraint(
            "NOT is_electronic OR ("
            "timbrado_number IS NOT NULL AND "
            "establishment_code IS NOT NULL AND "
            "point_of_issue_code IS NOT NULL AND "
            "sifen_document_type IS NOT NULL AND "
            "sifen_emission_type IS NOT NULL AND "
            "sifen_document_number IS NOT NULL AND "
            "sifen_cdc IS NOT NULL AND "
            "sifen_security_code IS NOT NULL"
            ")",
            name="electronic_identity_complete",
        ),
        CheckConstraint(
            "sifen_status IN ('NOT_SENT', 'PENDING', 'ACCEPTED', 'REJECTED', 'CANCELLED')",
            name="sifen_status",
        ),
        UniqueConstraint("sifen_cdc", name="sifen_cdc"),
        UniqueConstraint(
            "timbrado_number",
            "establishment_code",
            "point_of_issue_code",
            "sifen_document_type",
            "sifen_emission_type",
            "sifen_document_number",
            "sifen_series",
            name="sifen_document_identity",
        ),
        Index("ix_document_partner_id", "partner_id"),
        Index("ix_document_issued_at", "issued_at"),
        {"schema": CORE_SCHEMA},
    )

    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", server_default=text("'DRAFT'")
    )
    created_by_actor: Mapped[str] = mapped_column(String(100), nullable=False)
    partner_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{CORE_SCHEMA}.partner.id", ondelete="RESTRICT"), nullable=False
    )
    associated_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{CORE_SCHEMA}.document.id", ondelete="RESTRICT")
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    partner_reference: Mapped[str | None] = mapped_column(String(100))

    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    functional_currency_code: Mapped[str] = mapped_column(
        String(3), nullable=False, default="PYG", server_default=text("'PYG'")
    )
    exchange_rate: Mapped[Decimal] = mapped_column(
        EXCHANGE_RATE_NUMERIC, nullable=False, default=1, server_default=text("1")
    )
    subtotal: Mapped[Decimal] = mapped_column(
        MONEY_NUMERIC, nullable=False, server_default=text("0")
    )
    tax_total: Mapped[Decimal] = mapped_column(
        MONEY_NUMERIC, nullable=False, server_default=text("0")
    )
    total: Mapped[Decimal] = mapped_column(
        MONEY_NUMERIC, nullable=False, server_default=text("0")
    )
    functional_subtotal: Mapped[Decimal] = mapped_column(
        MONEY_NUMERIC, nullable=False, server_default=text("0")
    )
    functional_tax_total: Mapped[Decimal] = mapped_column(
        MONEY_NUMERIC, nullable=False, server_default=text("0")
    )
    functional_total: Mapped[Decimal] = mapped_column(
        MONEY_NUMERIC, nullable=False, server_default=text("0")
    )
    total_quantity: Mapped[Decimal] = mapped_column(
        QUANTITY_NUMERIC, nullable=False, server_default=text("0")
    )

    issuer_ruc: Mapped[str] = mapped_column(String(8), nullable=False)
    issuer_dv: Mapped[str] = mapped_column(String(1), nullable=False)
    issuer_legal_name: Mapped[str] = mapped_column(String(250), nullable=False)
    partner_ruc: Mapped[str] = mapped_column(String(8), nullable=False)
    partner_dv: Mapped[str] = mapped_column(String(1), nullable=False)
    partner_legal_name: Mapped[str] = mapped_column(String(250), nullable=False)

    is_electronic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    timbrado_number: Mapped[str | None] = mapped_column(String(8))
    establishment_code: Mapped[str | None] = mapped_column(String(3))
    point_of_issue_code: Mapped[str | None] = mapped_column(String(3))
    sifen_document_type: Mapped[str | None] = mapped_column(String(2))
    sifen_emission_type: Mapped[str | None] = mapped_column(String(1))
    sifen_document_number: Mapped[str | None] = mapped_column(String(7))
    sifen_series: Mapped[str] = mapped_column(
        String(2), nullable=False, default="", server_default=text("''")
    )
    sifen_cdc: Mapped[str | None] = mapped_column(String(44))
    sifen_security_code: Mapped[str | None] = mapped_column(String(9))
    sifen_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="NOT_SENT", server_default=text("'NOT_SENT'")
    )
    sifen_result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    partner: Mapped[Partner] = relationship(back_populates="documents")
    associated_document: Mapped[Document | None] = relationship(remote_side="Document.id")
    items: Mapped[list[DocumentItem]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentItem.line_number",
    )


class DocumentItem(CoreModelMixin, Base):
    """A taxed commercial-document line, retaining its financial snapshots."""

    __tablename__ = "document_item"
    __table_args__ = (
        CheckConstraint("line_number > 0", name="line_number_positive"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_nonnegative"),
        CheckConstraint("discount_amount >= 0", name="discount_nonnegative"),
        CheckConstraint(
            "line_subtotal >= 0 AND tax_amount >= 0 AND line_total >= 0",
            name="amounts_nonnegative",
        ),
        CheckConstraint("tax_rate >= 0 AND tax_rate <= 100", name="tax_rate_range"),
        CheckConstraint(
            "functional_unit_price >= 0 AND functional_subtotal >= 0 "
            "AND functional_tax_amount >= 0 AND functional_total >= 0",
            name="functional_amounts_nonnegative",
        ),
        UniqueConstraint("document_id", "line_number", name="document_line_number"),
        {"schema": CORE_SCHEMA},
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{CORE_SCHEMA}.document.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{CORE_SCHEMA}.product.id", ondelete="RESTRICT")
    )
    tax_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{CORE_SCHEMA}.tax.id", ondelete="RESTRICT"), nullable=False
    )
    product_code: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    unit_of_measure: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY_NUMERIC, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY_NUMERIC, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(
        MONEY_NUMERIC, nullable=False, server_default=text("0")
    )
    line_subtotal: Mapped[Decimal] = mapped_column(MONEY_NUMERIC, nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(TAX_RATE_NUMERIC, nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(MONEY_NUMERIC, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(MONEY_NUMERIC, nullable=False)
    functional_unit_price: Mapped[Decimal] = mapped_column(MONEY_NUMERIC, nullable=False)
    functional_subtotal: Mapped[Decimal] = mapped_column(MONEY_NUMERIC, nullable=False)
    functional_tax_amount: Mapped[Decimal] = mapped_column(MONEY_NUMERIC, nullable=False)
    functional_total: Mapped[Decimal] = mapped_column(MONEY_NUMERIC, nullable=False)

    document: Mapped[Document] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship(foreign_keys=[product_id])
    tax: Mapped[Tax] = relationship(foreign_keys=[tax_id])
