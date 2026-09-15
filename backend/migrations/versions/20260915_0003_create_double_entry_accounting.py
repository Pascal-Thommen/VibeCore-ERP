"""Create protected double-entry journal entry and journal line tables.

Revision ID: 20260915_0003
Revises: 20260915_0002
Create Date: 2026-09-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.core.financial_types import EXCHANGE_RATE_NUMERIC, MONEY_NUMERIC

# revision identifiers, used by Alembic.
revision: str = "20260915_0003"
down_revision: str | None = "20260915_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _audit_columns() -> list[sa.Column[object]]:
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
    """Create the Core journal ledger with database-enforced posting invariants."""
    op.create_table(
        "journal_entry",
        *_audit_columns(),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'DRAFT'"),
        ),
        sa.Column("created_by_actor", sa.String(length=100), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reverses_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column(
            "functional_currency_code",
            sa.String(length=3),
            nullable=False,
            server_default=sa.text("'PYG'"),
        ),
        sa.Column(
            "exchange_rate",
            EXCHANGE_RATE_NUMERIC,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by_actor", sa.String(length=100), nullable=True),
        sa.Column("posted_by_role", sa.String(length=20), nullable=True),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PENDING_APPROVAL', 'POSTED')",
            name=op.f("ck_journal_entry_status"),
        ),
        sa.CheckConstraint(
            "currency_code ~ '^[A-Z]{3}$'", name=op.f("ck_journal_entry_currency_code_format")
        ),
        sa.CheckConstraint(
            "functional_currency_code ~ '^[A-Z]{3}$'",
            name=op.f("ck_journal_entry_functional_currency_code_format"),
        ),
        sa.CheckConstraint(
            "functional_currency_code = 'PYG'",
            name=op.f("ck_journal_entry_functional_currency_code_pyg"),
        ),
        sa.CheckConstraint(
            "exchange_rate > 0", name=op.f("ck_journal_entry_exchange_rate_positive")
        ),
        sa.CheckConstraint(
            "currency_code <> 'PYG' OR exchange_rate = 1",
            name=op.f("ck_journal_entry_pyg_exchange_rate_one"),
        ),
        sa.CheckConstraint(
            "length(btrim(description)) > 0", name=op.f("ck_journal_entry_description_nonempty")
        ),
        sa.CheckConstraint(
            "(status = 'POSTED' AND posted_at IS NOT NULL AND posted_by_actor IS NOT NULL "
            "AND posted_by_role IS NOT NULL) OR "
            "(status <> 'POSTED' AND posted_at IS NULL AND posted_by_actor IS NULL "
            "AND posted_by_role IS NULL)",
            name=op.f("ck_journal_entry_posting_facts_match_status"),
        ),
        sa.CheckConstraint(
            "posted_by_actor IS NULL OR posted_by_actor <> created_by_actor",
            name=op.f("ck_journal_entry_poster_differs_from_creator"),
        ),
        sa.CheckConstraint(
            "posted_by_actor IS NULL OR posted_by_actor NOT IN ('AI_AGENT', 'SYSTEM_AGENT')",
            name=op.f("ck_journal_entry_poster_is_human"),
        ),
        sa.CheckConstraint(
            "posted_by_role IS NULL OR posted_by_role IN ('ADMIN', 'ACCOUNTANT')",
            name=op.f("ck_journal_entry_poster_role_is_eligible"),
        ),
        sa.CheckConstraint(
            "reverses_entry_id IS NULL OR reverses_entry_id <> id",
            name=op.f("ck_journal_entry_not_self_reversal"),
        ),
        sa.ForeignKeyConstraint(
            ["reverses_entry_id"],
            ["core.journal_entry.id"],
            name=op.f("fk_journal_entry_reverses_entry_id_journal_entry"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["core.document.id"],
            name=op.f("fk_journal_entry_source_document_id_document"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_entry")),
        schema="core",
    )
    op.create_index(
        op.f("ix_journal_entry_entry_date"), "journal_entry", ["entry_date"], schema="core"
    )
    op.create_index(op.f("ix_journal_entry_status"), "journal_entry", ["status"], schema="core")
    op.create_index(
        op.f("ix_journal_entry_source_document_id"),
        "journal_entry",
        ["source_document_id"],
        schema="core",
    )

    op.create_table(
        "journal_line",
        *_audit_columns(),
        sa.Column("journal_entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("debit", MONEY_NUMERIC, nullable=False),
        sa.Column("credit", MONEY_NUMERIC, nullable=False),
        sa.Column("functional_debit", MONEY_NUMERIC, nullable=False),
        sa.Column("functional_credit", MONEY_NUMERIC, nullable=False),
        sa.CheckConstraint("line_number > 0", name=op.f("ck_journal_line_line_number_positive")),
        sa.CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name=op.f("ck_journal_line_exactly_one_transaction_side"),
        ),
        sa.CheckConstraint(
            "(functional_debit > 0 AND functional_credit = 0) OR "
            "(functional_credit > 0 AND functional_debit = 0)",
            name=op.f("ck_journal_line_exactly_one_functional_side"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["core.account.id"],
            name=op.f("fk_journal_line_account_id_account"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["core.journal_entry.id"],
            name=op.f("fk_journal_line_journal_entry_id_journal_entry"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_line")),
        sa.UniqueConstraint(
            "journal_entry_id",
            "line_number",
            name=op.f("uq_journal_line_journal_entry_line_number"),
        ),
        schema="core",
    )
    op.create_index(
        op.f("ix_journal_line_account_id"),
        "journal_line",
        ["account_id"],
        schema="core",
    )

    op.execute(
        """
        CREATE FUNCTION core.enforce_journal_entry_lifecycle()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'DRAFT' THEN
                    RAISE EXCEPTION 'journal entries must be created as DRAFT'
                        USING ERRCODE = '55000';
                END IF;
                RETURN NEW;
            END IF;

            IF OLD.status = 'POSTED' THEN
                RAISE EXCEPTION 'posted journal entries are immutable'
                    USING ERRCODE = '55000';
            END IF;

            IF OLD.status = 'PENDING_APPROVAL' THEN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'pending journal entries are frozen until posting'
                        USING ERRCODE = '55000';
                END IF;
                IF NEW.status <> 'POSTED'
                   OR (to_jsonb(NEW) - ARRAY[
                       'status', 'posted_at', 'posted_by_actor', 'posted_by_role', 'updated_at'
                   ])
                      IS DISTINCT FROM
                      (to_jsonb(OLD) - ARRAY[
                          'status', 'posted_at', 'posted_by_actor', 'posted_by_role', 'updated_at'
                      ]) THEN
                    RAISE EXCEPTION 'pending journal entries are frozen until posting'
                        USING ERRCODE = '55000';
                END IF;
                RETURN NEW;
            END IF;

            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;

            IF OLD.status = 'DRAFT' AND NEW.status NOT IN ('DRAFT', 'PENDING_APPROVAL') THEN
                RAISE EXCEPTION 'invalid journal entry lifecycle transition from % to %',
                    OLD.status, NEW.status USING ERRCODE = '55000';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER journal_entry_lifecycle_guard
        BEFORE INSERT OR UPDATE OR DELETE ON core.journal_entry
        FOR EACH ROW EXECUTE FUNCTION core.enforce_journal_entry_lifecycle();
        """
    )
    op.execute(
        """
        CREATE FUNCTION core.verify_posted_journal_entry_balance()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            line_count integer;
            debit_total numeric;
            credit_total numeric;
            functional_debit_total numeric;
            functional_credit_total numeric;
            reversal_status text;
        BEGIN
            IF NEW.status <> 'POSTED' THEN
                RETURN NEW;
            END IF;

            SELECT
                count(*),
                COALESCE(sum(debit), 0),
                COALESCE(sum(credit), 0),
                COALESCE(sum(functional_debit), 0),
                COALESCE(sum(functional_credit), 0)
            INTO
                line_count,
                debit_total,
                credit_total,
                functional_debit_total,
                functional_credit_total
            FROM core.journal_line
            WHERE journal_entry_id = NEW.id;

            IF line_count < 2
               OR debit_total <> credit_total
               OR functional_debit_total <> functional_credit_total THEN
                RAISE EXCEPTION 'posted journal entry % is not balanced', NEW.id
                    USING ERRCODE = '23514';
            END IF;
            IF NEW.reverses_entry_id IS NOT NULL THEN
                SELECT status INTO reversal_status
                FROM core.journal_entry
                WHERE id = NEW.reverses_entry_id;
                IF reversal_status <> 'POSTED' THEN
                    RAISE EXCEPTION 'reversing journal entry % must reference a posted entry',
                        NEW.id
                        USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER journal_entry_posted_balance
        AFTER INSERT OR UPDATE ON core.journal_entry
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION core.verify_posted_journal_entry_balance();
        """
    )
    op.execute(
        """
        CREATE FUNCTION core.prevent_posted_journal_line_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            old_entry_status text;
            new_entry_status text;
        BEGIN
            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                SELECT status INTO old_entry_status
                FROM core.journal_entry
                WHERE id = OLD.journal_entry_id;
            END IF;
            IF TG_OP IN ('INSERT', 'UPDATE') THEN
                SELECT status INTO new_entry_status
                FROM core.journal_entry
                WHERE id = NEW.journal_entry_id;
            END IF;

            IF old_entry_status IN ('PENDING_APPROVAL', 'POSTED')
               OR new_entry_status IN ('PENDING_APPROVAL', 'POSTED') THEN
                RAISE EXCEPTION 'pending and posted journal entries and their lines are immutable'
                    USING ERRCODE = '55000';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER journal_line_posted_immutability_guard
        BEFORE INSERT OR UPDATE OR DELETE ON core.journal_line
        FOR EACH ROW EXECUTE FUNCTION core.prevent_posted_journal_line_mutation();
        """
    )


def downgrade() -> None:
    """Remove accounting tables and their database-enforced invariants."""
    op.execute("DROP TRIGGER IF EXISTS journal_line_posted_immutability_guard ON core.journal_line")
    op.execute("DROP FUNCTION IF EXISTS core.prevent_posted_journal_line_mutation()")
    op.execute("DROP TRIGGER IF EXISTS journal_entry_posted_balance ON core.journal_entry")
    op.execute("DROP FUNCTION IF EXISTS core.verify_posted_journal_entry_balance()")
    op.execute("DROP TRIGGER IF EXISTS journal_entry_lifecycle_guard ON core.journal_entry")
    op.execute("DROP FUNCTION IF EXISTS core.enforce_journal_entry_lifecycle()")
    op.drop_index(op.f("ix_journal_line_account_id"), table_name="journal_line", schema="core")
    op.drop_table("journal_line", schema="core")
    op.drop_index(
        op.f("ix_journal_entry_source_document_id"), table_name="journal_entry", schema="core"
    )
    op.drop_index(op.f("ix_journal_entry_status"), table_name="journal_entry", schema="core")
    op.drop_index(op.f("ix_journal_entry_entry_date"), table_name="journal_entry", schema="core")
    op.drop_table("journal_entry", schema="core")
