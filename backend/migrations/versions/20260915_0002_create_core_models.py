"""Create canonical Core master data and commercial-document tables.

Revision ID: 20260915_0002
Revises: 20260914_0001
Create Date: 2026-09-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.core.financial_types import (
    EXCHANGE_RATE_NUMERIC,
    MONEY_NUMERIC,
    QUANTITY_NUMERIC,
    TAX_RATE_NUMERIC,
)

# revision identifiers, used by Alembic.
revision: str = "20260915_0002"
down_revision: str | None = "20260914_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _audit_columns() -> list[sa.Column[object]]:
    """Return the columns every extensible Core table must carry."""
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    ]


def upgrade() -> None:
    """Create the first protected, deterministic Core data model."""
    op.create_table(
        "partner",
        *_audit_columns(),
        sa.Column("ruc", sa.String(length=8), nullable=False),
        sa.Column("dv", sa.String(length=1), nullable=False),
        sa.Column("legal_name", sa.String(length=250), nullable=False),
        sa.Column("trade_name", sa.String(length=250), nullable=True),
        sa.Column("is_customer", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_supplier", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint("ruc ~ '^[0-9]{5,8}$'", name=op.f("ck_partner_ruc_format")),
        sa.CheckConstraint("dv ~ '^[0-9]$'", name=op.f("ck_partner_dv_format")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partner")),
        sa.UniqueConstraint("ruc", "dv", name=op.f("uq_partner_ruc_dv")),
        schema="core",
    )

    op.create_table(
        "account",
        *_audit_columns(),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("account_type", sa.String(length=40), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reconcile", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("allow_posting", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint(
            "code ~ '^[0-9]+(\\.[0-9]+)*$'", name=op.f("ck_account_code_format")
        ),
        sa.CheckConstraint(
            "account_type IN ("
            "'asset_current', 'asset_fixed', 'asset_non_current', 'asset_prepayments', "
            "'asset_receivable', 'equity', 'equity_unaffected', 'expense', "
            "'expense_depreciation', 'income', 'income_other', 'liability_current', "
            "'liability_non_current', 'liability_payable'"
            ")",
            name=op.f("ck_account_account_type"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["core.account.id"],
            name=op.f("fk_account_parent_id_account"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account")),
        sa.UniqueConstraint("code", name=op.f("uq_account_code")),
        schema="core",
    )

    op.create_table(
        "tax",
        *_audit_columns(),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("rate", TAX_RATE_NUMERIC, nullable=False),
        sa.Column("scope", sa.String(length=12), nullable=False, server_default=sa.text("'BOTH'")),
        sa.Column("sales_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("purchase_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint("rate >= 0 AND rate <= 100", name=op.f("ck_tax_rate_range")),
        sa.CheckConstraint(
            "scope IN ('SALES', 'PURCHASE', 'BOTH')", name=op.f("ck_tax_scope")
        ),
        sa.ForeignKeyConstraint(
            ["purchase_account_id"],
            ["core.account.id"],
            name=op.f("fk_tax_purchase_account_id_account"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sales_account_id"],
            ["core.account.id"],
            name=op.f("fk_tax_sales_account_id_account"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tax")),
        sa.UniqueConstraint("code", name=op.f("uq_tax_code")),
        schema="core",
    )

    op.create_table(
        "product",
        *_audit_columns(),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=250), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=20), nullable=False),
        sa.Column("is_stock_item", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_sales_item", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_purchase_item", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("standard_price", MONEY_NUMERIC, nullable=False, server_default=sa.text("0")),
        sa.Column("valuation_rate", MONEY_NUMERIC, nullable=False, server_default=sa.text("0")),
        sa.Column("weight_per_unit", QUANTITY_NUMERIC, nullable=True),
        sa.Column("weight_unit", sa.String(length=20), nullable=True),
        sa.Column("default_tax_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("income_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expense_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint(
            "standard_price >= 0", name=op.f("ck_product_standard_price_nonnegative")
        ),
        sa.CheckConstraint(
            "valuation_rate >= 0", name=op.f("ck_product_valuation_rate_nonnegative")
        ),
        sa.CheckConstraint(
            "weight_per_unit IS NULL OR weight_per_unit >= 0",
            name=op.f("ck_product_weight_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["default_tax_id"],
            ["core.tax.id"],
            name=op.f("fk_product_default_tax_id_tax"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["expense_account_id"],
            ["core.account.id"],
            name=op.f("fk_product_expense_account_id_account"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["income_account_id"],
            ["core.account.id"],
            name=op.f("fk_product_income_account_id_account"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product")),
        sa.UniqueConstraint("sku", name=op.f("uq_product_sku")),
        schema="core",
    )

    op.create_table(
        "document",
        *_audit_columns(),
        sa.Column("document_type", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default=sa.text("'DRAFT'")
        ),
        sa.Column("created_by_actor", sa.String(length=100), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("associated_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("partner_reference", sa.String(length=100), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column(
            "functional_currency_code",
            sa.String(length=3),
            nullable=False,
            server_default=sa.text("'PYG'"),
        ),
        sa.Column(
            "exchange_rate", EXCHANGE_RATE_NUMERIC, nullable=False, server_default=sa.text("1")
        ),
        sa.Column("subtotal", MONEY_NUMERIC, nullable=False, server_default=sa.text("0")),
        sa.Column("tax_total", MONEY_NUMERIC, nullable=False, server_default=sa.text("0")),
        sa.Column("total", MONEY_NUMERIC, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "functional_subtotal", MONEY_NUMERIC, nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "functional_tax_total", MONEY_NUMERIC, nullable=False, server_default=sa.text("0")
        ),
        sa.Column("functional_total", MONEY_NUMERIC, nullable=False, server_default=sa.text("0")),
        sa.Column("total_quantity", QUANTITY_NUMERIC, nullable=False, server_default=sa.text("0")),
        sa.Column("issuer_ruc", sa.String(length=8), nullable=False),
        sa.Column("issuer_dv", sa.String(length=1), nullable=False),
        sa.Column("issuer_legal_name", sa.String(length=250), nullable=False),
        sa.Column("partner_ruc", sa.String(length=8), nullable=False),
        sa.Column("partner_dv", sa.String(length=1), nullable=False),
        sa.Column("partner_legal_name", sa.String(length=250), nullable=False),
        sa.Column("is_electronic", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("timbrado_number", sa.String(length=8), nullable=True),
        sa.Column("establishment_code", sa.String(length=3), nullable=True),
        sa.Column("point_of_issue_code", sa.String(length=3), nullable=True),
        sa.Column("sifen_document_type", sa.String(length=2), nullable=True),
        sa.Column("sifen_emission_type", sa.String(length=1), nullable=True),
        sa.Column("sifen_document_number", sa.String(length=7), nullable=True),
        sa.Column(
            "sifen_series", sa.String(length=2), nullable=False, server_default=sa.text("''")
        ),
        sa.Column("sifen_cdc", sa.String(length=44), nullable=True),
        sa.Column("sifen_security_code", sa.String(length=9), nullable=True),
        sa.Column(
            "sifen_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'NOT_SENT'"),
        ),
        sa.Column(
            "sifen_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "document_type IN ('INVOICE', 'CREDIT_NOTE', 'DEBIT_NOTE', 'RECEIPT', 'REMITTANCE')",
            name=op.f("ck_document_document_type"),
        ),
        sa.CheckConstraint(
            "direction IN ('SALES', 'PURCHASE')", name=op.f("ck_document_direction")
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PENDING_APPROVAL', 'POSTED', 'CANCELLED', 'REJECTED')",
            name=op.f("ck_document_status"),
        ),
        sa.CheckConstraint(
            "currency_code ~ '^[A-Z]{3}$'", name=op.f("ck_document_currency_code_format")
        ),
        sa.CheckConstraint(
            "functional_currency_code ~ '^[A-Z]{3}$'",
            name=op.f("ck_document_functional_currency_code_format"),
        ),
        sa.CheckConstraint("exchange_rate > 0", name=op.f("ck_document_exchange_rate_positive")),
        sa.CheckConstraint(
            "subtotal >= 0 AND tax_total >= 0 AND total >= 0",
            name=op.f("ck_document_amounts_nonnegative"),
        ),
        sa.CheckConstraint(
            "functional_subtotal >= 0 AND functional_tax_total >= 0 AND functional_total >= 0",
            name=op.f("ck_document_functional_amounts_nonnegative"),
        ),
        sa.CheckConstraint(
            "total_quantity >= 0", name=op.f("ck_document_total_quantity_nonnegative")
        ),
        sa.CheckConstraint(
            "issuer_ruc ~ '^[0-9]{5,8}$'", name=op.f("ck_document_issuer_ruc_format")
        ),
        sa.CheckConstraint("issuer_dv ~ '^[0-9]$'", name=op.f("ck_document_issuer_dv_format")),
        sa.CheckConstraint(
            "partner_ruc ~ '^[0-9]{5,8}$'", name=op.f("ck_document_partner_ruc_format")
        ),
        sa.CheckConstraint(
            "partner_dv ~ '^[0-9]$'", name=op.f("ck_document_partner_dv_format")
        ),
        sa.CheckConstraint(
            "(timbrado_number IS NULL OR timbrado_number ~ '^[0-9]{8}$') AND "
            "(establishment_code IS NULL OR establishment_code ~ '^[0-9]{3}$') AND "
            "(point_of_issue_code IS NULL OR point_of_issue_code ~ '^[0-9]{3}$') AND "
            "(sifen_document_type IS NULL OR sifen_document_type ~ '^[0-9]{2}$') AND "
            "(sifen_emission_type IS NULL OR sifen_emission_type ~ '^[0-9]$') AND "
            "(sifen_document_number IS NULL OR sifen_document_number ~ '^[0-9]{7}$') AND "
            "(sifen_cdc IS NULL OR sifen_cdc ~ '^[0-9]{44}$') AND "
            "(sifen_security_code IS NULL OR sifen_security_code ~ '^[0-9]{9}$') AND "
            "sifen_series ~ '^$|^[A-Z]{2}$'",
            name=op.f("ck_document_sifen_identity_format"),
        ),
        sa.CheckConstraint(
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
            name=op.f("ck_document_electronic_identity_complete"),
        ),
        sa.CheckConstraint(
            "sifen_status IN ('NOT_SENT', 'PENDING', 'ACCEPTED', 'REJECTED', 'CANCELLED')",
            name=op.f("ck_document_sifen_status"),
        ),
        sa.ForeignKeyConstraint(
            ["associated_document_id"],
            ["core.document.id"],
            name=op.f("fk_document_associated_document_id_document"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["core.partner.id"],
            name=op.f("fk_document_partner_id_partner"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document")),
        sa.UniqueConstraint("sifen_cdc", name=op.f("uq_document_sifen_cdc")),
        sa.UniqueConstraint(
            "timbrado_number",
            "establishment_code",
            "point_of_issue_code",
            "sifen_document_type",
            "sifen_emission_type",
            "sifen_document_number",
            "sifen_series",
            name=op.f("uq_document_sifen_document_identity"),
        ),
        schema="core",
    )
    op.create_index(op.f("ix_document_partner_id"), "document", ["partner_id"], schema="core")
    op.create_index(op.f("ix_document_issued_at"), "document", ["issued_at"], schema="core")

    op.create_table(
        "document_item",
        *_audit_columns(),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tax_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_code", sa.String(length=100), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("unit_of_measure", sa.String(length=20), nullable=False),
        sa.Column("quantity", QUANTITY_NUMERIC, nullable=False),
        sa.Column("unit_price", MONEY_NUMERIC, nullable=False),
        sa.Column("discount_amount", MONEY_NUMERIC, nullable=False, server_default=sa.text("0")),
        sa.Column("line_subtotal", MONEY_NUMERIC, nullable=False),
        sa.Column("tax_rate", TAX_RATE_NUMERIC, nullable=False),
        sa.Column("tax_amount", MONEY_NUMERIC, nullable=False),
        sa.Column("line_total", MONEY_NUMERIC, nullable=False),
        sa.Column("functional_unit_price", MONEY_NUMERIC, nullable=False),
        sa.Column("functional_subtotal", MONEY_NUMERIC, nullable=False),
        sa.Column("functional_tax_amount", MONEY_NUMERIC, nullable=False),
        sa.Column("functional_total", MONEY_NUMERIC, nullable=False),
        sa.CheckConstraint(
            "line_number > 0", name=op.f("ck_document_item_line_number_positive")
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_document_item_quantity_positive")),
        sa.CheckConstraint(
            "unit_price >= 0", name=op.f("ck_document_item_unit_price_nonnegative")
        ),
        sa.CheckConstraint(
            "discount_amount >= 0", name=op.f("ck_document_item_discount_nonnegative")
        ),
        sa.CheckConstraint(
            "line_subtotal >= 0 AND tax_amount >= 0 AND line_total >= 0",
            name=op.f("ck_document_item_amounts_nonnegative"),
        ),
        sa.CheckConstraint(
            "tax_rate >= 0 AND tax_rate <= 100", name=op.f("ck_document_item_tax_rate_range")
        ),
        sa.CheckConstraint(
            "functional_unit_price >= 0 AND functional_subtotal >= 0 "
            "AND functional_tax_amount >= 0 AND functional_total >= 0",
            name=op.f("ck_document_item_functional_amounts_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["core.document.id"],
            name=op.f("fk_document_item_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["core.product.id"],
            name=op.f("fk_document_item_product_id_product"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tax_id"],
            ["core.tax.id"],
            name=op.f("fk_document_item_tax_id_tax"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_item")),
        sa.UniqueConstraint(
            "document_id", "line_number", name=op.f("uq_document_item_document_line_number")
        ),
        schema="core",
    )


def downgrade() -> None:
    """Remove Core business tables without touching the protected schemas."""
    op.drop_table("document_item", schema="core")
    op.drop_index(op.f("ix_document_issued_at"), table_name="document", schema="core")
    op.drop_index(op.f("ix_document_partner_id"), table_name="document", schema="core")
    op.drop_table("document", schema="core")
    op.drop_table("product", schema="core")
    op.drop_table("tax", schema="core")
    op.drop_table("account", schema="core")
    op.drop_table("partner", schema="core")
