"""Create the protected PostgreSQL transactional outbox.

Revision ID: 20260915_0004
Revises: 20260915_0003
Create Date: 2026-09-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260915_0004"
down_revision: str | None = "20260915_0003"
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
    """Create immutable event facts and publisher-owned delivery state."""
    op.create_table(
        "outbox_event",
        *_audit_columns(),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'PROCESSED', 'FAILED')",
            name=op.f("ck_outbox_event_status"),
        ),
        sa.CheckConstraint(
            "event_version > 0", name=op.f("ck_outbox_event_event_version_positive")
        ),
        sa.CheckConstraint(
            "length(btrim(event_type)) > 0", name=op.f("ck_outbox_event_event_type_nonempty")
        ),
        sa.CheckConstraint(
            "length(btrim(aggregate_type)) > 0",
            name=op.f("ck_outbox_event_aggregate_type_nonempty"),
        ),
        sa.CheckConstraint(
            "length(btrim(idempotency_key)) > 0",
            name=op.f("ck_outbox_event_idempotency_key_nonempty"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'", name=op.f("ck_outbox_event_payload_is_object")
        ),
        sa.CheckConstraint(
            "(NOT payload ? 'meta' OR jsonb_typeof(payload -> 'meta') = 'object') AND "
            "(NOT payload ? 'custom_data' OR jsonb_typeof(payload -> 'custom_data') = 'object')",
            name=op.f("ck_outbox_event_payload_extensions_are_objects"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name=op.f("ck_outbox_event_attempt_count_nonnegative")
        ),
        sa.CheckConstraint(
            "(status = 'PROCESSED' AND processed_at IS NOT NULL) OR "
            "(status <> 'PROCESSED' AND processed_at IS NULL)",
            name=op.f("ck_outbox_event_processed_at_matches_status"),
        ),
        sa.CheckConstraint(
            "status <> 'FAILED' OR (last_error IS NOT NULL AND length(btrim(last_error)) > 0)",
            name=op.f("ck_outbox_event_failed_events_have_error"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_event")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_outbox_event_idempotency_key")),
        schema="core",
    )
    op.create_index(
        op.f("ix_outbox_event_pending"),
        "outbox_event",
        ["created_at"],
        unique=False,
        schema="core",
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        op.f("ix_outbox_event_aggregate"),
        "outbox_event",
        ["aggregate_type", "aggregate_id"],
        unique=False,
        schema="core",
    )
    op.create_index(
        op.f("ix_outbox_event_correlation_id"),
        "outbox_event",
        ["correlation_id"],
        unique=False,
        schema="core",
    )

    op.execute(
        """
        CREATE FUNCTION core.enforce_outbox_event_lifecycle()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'PENDING'
                   OR NEW.processed_at IS NOT NULL
                   OR NEW.attempt_count <> 0 THEN
                    RAISE EXCEPTION 'outbox events must be created as unattempted PENDING events'
                        USING ERRCODE = '55000';
                END IF;
                RETURN NEW;
            END IF;

            IF OLD.status = 'PROCESSED' THEN
                RAISE EXCEPTION 'processed outbox events are immutable'
                    USING ERRCODE = '55000';
            END IF;

            IF (to_jsonb(NEW) - ARRAY[
                    'status', 'attempt_count', 'last_attempt_at', 'last_error',
                    'processed_at', 'updated_at'
                ])
                IS DISTINCT FROM
                (to_jsonb(OLD) - ARRAY[
                    'status', 'attempt_count', 'last_attempt_at', 'last_error',
                    'processed_at', 'updated_at'
                ]) THEN
                RAISE EXCEPTION 'outbox event facts are immutable'
                    USING ERRCODE = '55000';
            END IF;

            IF NEW.status = OLD.status THEN
                RETURN NEW;
            END IF;

            IF OLD.status = 'PENDING' AND NEW.status = 'PROCESSING' THEN
                IF NEW.attempt_count <> OLD.attempt_count + 1
                   OR NEW.last_attempt_at IS NULL THEN
                    RAISE EXCEPTION 'claiming an outbox event must record its attempt'
                        USING ERRCODE = '55000';
                END IF;
                RETURN NEW;
            END IF;

            IF OLD.status = 'PROCESSING'
               AND NEW.status IN ('PENDING', 'PROCESSED', 'FAILED') THEN
                RETURN NEW;
            END IF;

            IF OLD.status = 'FAILED' AND NEW.status = 'PENDING' THEN
                RETURN NEW;
            END IF;

            RAISE EXCEPTION 'invalid outbox event lifecycle transition from % to %',
                OLD.status, NEW.status USING ERRCODE = '55000';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER outbox_event_lifecycle_guard
        BEFORE INSERT OR UPDATE ON core.outbox_event
        FOR EACH ROW EXECUTE FUNCTION core.enforce_outbox_event_lifecycle();
        """
    )


def downgrade() -> None:
    """Remove the outbox without affecting already-migrated finance tables."""
    op.execute("DROP TRIGGER IF EXISTS outbox_event_lifecycle_guard ON core.outbox_event")
    op.execute("DROP FUNCTION IF EXISTS core.enforce_outbox_event_lifecycle()")
    op.drop_index(op.f("ix_outbox_event_correlation_id"), table_name="outbox_event", schema="core")
    op.drop_index(op.f("ix_outbox_event_aggregate"), table_name="outbox_event", schema="core")
    op.drop_index(op.f("ix_outbox_event_pending"), table_name="outbox_event", schema="core")
    op.drop_table("outbox_event", schema="core")
