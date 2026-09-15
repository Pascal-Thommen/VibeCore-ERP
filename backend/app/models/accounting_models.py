"""Double-entry accounting models in the protected ``core`` schema.

Journal entry currency and exchange-rate values are retained on the entry
header.  Each line keeps the resulting functional-currency amount as an
immutable snapshot once the entry is posted.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.financial_types import EXCHANGE_RATE_NUMERIC, MONEY_NUMERIC
from app.db.base import Base, CORE_SCHEMA
from app.models.core_models import CoreModelMixin


class JournalEntry(CoreModelMixin, Base):
    """A draft, approval-pending, or posted double-entry journal header."""

    __tablename__ = "journal_entry"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_APPROVAL', 'POSTED')", name="status"
        ),
        CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="currency_code_format"),
        CheckConstraint(
            "functional_currency_code ~ '^[A-Z]{3}$'", name="functional_currency_code_format"
        ),
        CheckConstraint(
            "functional_currency_code = 'PYG'", name="functional_currency_code_pyg"
        ),
        CheckConstraint("exchange_rate > 0", name="exchange_rate_positive"),
        CheckConstraint(
            "currency_code <> 'PYG' OR exchange_rate = 1", name="pyg_exchange_rate_one"
        ),
        CheckConstraint("length(btrim(description)) > 0", name="description_nonempty"),
        CheckConstraint(
            "(status = 'POSTED' AND posted_at IS NOT NULL AND posted_by_actor IS NOT NULL "
            "AND posted_by_role IS NOT NULL) OR "
            "(status <> 'POSTED' AND posted_at IS NULL AND posted_by_actor IS NULL "
            "AND posted_by_role IS NULL)",
            name="posting_facts_match_status",
        ),
        CheckConstraint(
            "posted_by_actor IS NULL OR posted_by_actor <> created_by_actor",
            name="poster_differs_from_creator",
        ),
        CheckConstraint(
            "posted_by_actor IS NULL OR posted_by_actor NOT IN ('AI_AGENT', 'SYSTEM_AGENT')",
            name="poster_is_human",
        ),
        CheckConstraint(
            "posted_by_role IS NULL OR posted_by_role IN ('ADMIN', 'ACCOUNTANT')",
            name="poster_role_is_eligible",
        ),
        CheckConstraint(
            "reverses_entry_id IS NULL OR reverses_entry_id <> id", name="not_self_reversal"
        ),
        Index("ix_journal_entry_entry_date", "entry_date"),
        Index("ix_journal_entry_status", "status"),
        Index("ix_journal_entry_source_document_id", "source_document_id"),
        {"schema": CORE_SCHEMA},
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT", server_default=text("'DRAFT'")
    )
    created_by_actor: Mapped[str] = mapped_column(String(100), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100))
    source_document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{CORE_SCHEMA}.document.id", ondelete="RESTRICT")
    )
    reverses_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(f"{CORE_SCHEMA}.journal_entry.id", ondelete="RESTRICT")
    )
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    functional_currency_code: Mapped[str] = mapped_column(
        String(3), nullable=False, default="PYG", server_default=text("'PYG'")
    )
    exchange_rate: Mapped[Decimal] = mapped_column(
        EXCHANGE_RATE_NUMERIC, nullable=False, default=1, server_default=text("1")
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by_actor: Mapped[str | None] = mapped_column(String(100))
    posted_by_role: Mapped[str | None] = mapped_column(String(20))

    lines: Mapped[list[JournalLine]] = relationship(
        back_populates="journal_entry",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="JournalLine.line_number",
    )
    reversing_entry: Mapped[JournalEntry | None] = relationship(
        remote_side="JournalEntry.id", foreign_keys=[reverses_entry_id]
    )


class JournalLine(CoreModelMixin, Base):
    """One debit or credit component of a journal entry."""

    __tablename__ = "journal_line"
    __table_args__ = (
        CheckConstraint("line_number > 0", name="line_number_positive"),
        CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="exactly_one_transaction_side",
        ),
        CheckConstraint(
            "(functional_debit > 0 AND functional_credit = 0) OR "
            "(functional_credit > 0 AND functional_debit = 0)",
            name="exactly_one_functional_side",
        ),
        UniqueConstraint(
            "journal_entry_id", "line_number", name="journal_entry_line_number"
        ),
        Index("ix_journal_line_account_id", "account_id"),
        {"schema": CORE_SCHEMA},
    )

    journal_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{CORE_SCHEMA}.journal_entry.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey(f"{CORE_SCHEMA}.account.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(500))
    debit: Mapped[Decimal] = mapped_column(MONEY_NUMERIC, nullable=False)
    credit: Mapped[Decimal] = mapped_column(MONEY_NUMERIC, nullable=False)
    functional_debit: Mapped[Decimal] = mapped_column(MONEY_NUMERIC, nullable=False)
    functional_credit: Mapped[Decimal] = mapped_column(MONEY_NUMERIC, nullable=False)

    journal_entry: Mapped[JournalEntry] = relationship(back_populates="lines")
