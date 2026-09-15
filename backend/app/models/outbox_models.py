"""Transactional-outbox persistence model for reliable Core integrations.

The publisher owns delivery state, while the event identity and payload are
immutable facts written alongside the business transition that produced them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CORE_SCHEMA
from app.models.core_models import CoreModelMixin


class OutboxEvent(CoreModelMixin, Base):
    """An immutable integration event with mutable delivery-state fields only."""

    __tablename__ = "outbox_event"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'PROCESSED', 'FAILED')", name="status"
        ),
        CheckConstraint("event_version > 0", name="event_version_positive"),
        CheckConstraint("length(btrim(event_type)) > 0", name="event_type_nonempty"),
        CheckConstraint("length(btrim(aggregate_type)) > 0", name="aggregate_type_nonempty"),
        CheckConstraint("length(btrim(idempotency_key)) > 0", name="idempotency_key_nonempty"),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="payload_is_object"),
        CheckConstraint(
            "(NOT payload ? 'meta' OR jsonb_typeof(payload -> 'meta') = 'object') AND "
            "(NOT payload ? 'custom_data' OR jsonb_typeof(payload -> 'custom_data') = 'object')",
            name="payload_extensions_are_objects",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            "(status = 'PROCESSED' AND processed_at IS NOT NULL) OR "
            "(status <> 'PROCESSED' AND processed_at IS NULL)",
            name="processed_at_matches_status",
        ),
        CheckConstraint(
            "status <> 'FAILED' OR (last_error IS NOT NULL AND length(btrim(last_error)) > 0)",
            name="failed_events_have_error",
        ),
        UniqueConstraint("idempotency_key"),
        Index(
            "ix_outbox_event_pending",
            "created_at",
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index("ix_outbox_event_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_outbox_event_correlation_id", "correlation_id"),
        {"schema": CORE_SCHEMA},
    )

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
