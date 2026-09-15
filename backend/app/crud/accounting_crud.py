"""Persistence operations that enforce Core double-entry accounting rules."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.core_crud import RelatedResourceNotFoundError, _money
from app.models import Account, Document, JournalEntry, JournalLine
from app.schemas.accounting_schemas import (
    JournalEntryCreate,
    JournalEntryPost,
    JournalEntryUpdate,
    JournalLineCreate,
    JournalLineUpdate,
)


class JournalEntryNotEditableError(Exception):
    """Raised when an operation would mutate a non-DRAFT journal entry."""


class JournalEntryStateError(Exception):
    """Raised when an entry lifecycle transition is invalid."""


def _schema_values(schema: Any) -> dict[str, Any]:
    return schema.model_dump(exclude_unset=True, by_alias=False)


async def _get_postable_account(session: AsyncSession, account_id: UUID) -> Account:
    account = await session.get(Account, account_id)
    if account is None:
        raise RelatedResourceNotFoundError("account")
    if not account.is_active or not account.allow_posting:
        raise ValueError("journal lines require an active account that allows posting")
    return account


async def _require_document_if_present(session: AsyncSession, document_id: UUID | None) -> None:
    if document_id is not None and await session.get(Document, document_id) is None:
        raise RelatedResourceNotFoundError("source document")


async def _require_posted_reversal_target(
    session: AsyncSession, reverses_entry_id: UUID | None
) -> None:
    if reverses_entry_id is None:
        return
    reversed_entry = await get_journal_entry(session, reverses_entry_id)
    if reversed_entry is None:
        raise RelatedResourceNotFoundError("reversed journal entry")
    if reversed_entry.status != "POSTED":
        raise ValueError("a reversing entry must reference a POSTED journal entry")


def _entry_is_balanced(entry: JournalEntry) -> bool:
    if len(entry.lines) < 2:
        return False
    debit = sum((line.debit for line in entry.lines), Decimal("0"))
    credit = sum((line.credit for line in entry.lines), Decimal("0"))
    functional_debit = sum((line.functional_debit for line in entry.lines), Decimal("0"))
    functional_credit = sum((line.functional_credit for line in entry.lines), Decimal("0"))
    return debit == credit and functional_debit == functional_credit


def _require_balanced_entry(entry: JournalEntry) -> None:
    if not _entry_is_balanced(entry):
        raise ValueError(
            "journal entries require at least two lines and equal debit and credit totals "
            "in transaction and functional currency"
        )


async def _require_postable_line_accounts(
    session: AsyncSession, journal_entry: JournalEntry
) -> None:
    for journal_line in journal_entry.lines:
        await _get_postable_account(session, journal_line.account_id)


def _assert_draft(entry: JournalEntry) -> None:
    if entry.status != "DRAFT":
        raise JournalEntryNotEditableError("only DRAFT journal entries can be changed or deleted")


async def get_journal_entry(
    session: AsyncSession, journal_entry_id: UUID
) -> JournalEntry | None:
    statement = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines))
        .where(JournalEntry.id == journal_entry_id)
    )
    return (await session.scalars(statement)).one_or_none()


async def list_journal_entries(
    session: AsyncSession, *, offset: int = 0, limit: int = 100
) -> list[JournalEntry]:
    statement = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines))
        .order_by(JournalEntry.entry_date.desc(), JournalEntry.id)
        .offset(offset)
        .limit(limit)
    )
    return list(await session.scalars(statement))


async def _line_values(
    session: AsyncSession,
    *,
    data: JournalLineCreate | JournalLineUpdate | dict[str, Any],
    exchange_rate: Decimal,
    existing: JournalLine | None = None,
) -> dict[str, Any]:
    raw_values = data if isinstance(data, dict) else _schema_values(data)
    existing_values = {
        "account_id": existing.account_id if existing else None,
        "description": existing.description if existing else None,
        "debit": existing.debit if existing else Decimal("0"),
        "credit": existing.credit if existing else Decimal("0"),
        "metadata_": existing.metadata_ if existing else {},
    }
    values = {**existing_values, **raw_values}
    if values["account_id"] is None:
        raise ValueError("account_id is required")
    await _get_postable_account(session, values["account_id"])

    debit = values["debit"]
    credit = values["credit"]
    if (debit > 0) == (credit > 0):
        raise ValueError("a journal line must have exactly one positive debit or credit amount")

    return {
        **values,
        "functional_debit": _money(debit * exchange_rate),
        "functional_credit": _money(credit * exchange_rate),
    }


async def _next_line_number(session: AsyncSession, journal_entry_id: UUID) -> int:
    maximum = await session.scalar(
        select(func.max(JournalLine.line_number)).where(
            JournalLine.journal_entry_id == journal_entry_id
        )
    )
    return int(maximum or 0) + 1


async def create_journal_entry(session: AsyncSession, data: JournalEntryCreate) -> JournalEntry:
    entry_values = _schema_values(data)
    line_data = entry_values.pop("lines")
    await _require_document_if_present(session, entry_values.get("source_document_id"))
    await _require_posted_reversal_target(session, entry_values.get("reverses_entry_id"))
    entry_values["status"] = "DRAFT"
    journal_entry = JournalEntry(**entry_values)
    session.add(journal_entry)
    await session.flush()

    for line_number, raw_line in enumerate(line_data, start=1):
        values = await _line_values(
            session,
            data=raw_line,
            exchange_rate=journal_entry.exchange_rate,
        )
        session.add(
            JournalLine(
                journal_entry_id=journal_entry.id,
                line_number=line_number,
                **values,
            )
        )
    await session.commit()
    return (await get_journal_entry(session, journal_entry.id))  # type: ignore[return-value]


async def update_journal_entry(
    session: AsyncSession, journal_entry_id: UUID, data: JournalEntryUpdate
) -> JournalEntry | None:
    journal_entry = await get_journal_entry(session, journal_entry_id)
    if journal_entry is None:
        return None
    _assert_draft(journal_entry)
    values = _schema_values(data)
    if "source_document_id" in values:
        await _require_document_if_present(session, values["source_document_id"])

    new_currency = values.get("currency_code", journal_entry.currency_code)
    new_exchange_rate = values.get("exchange_rate", journal_entry.exchange_rate)
    if new_currency == "PYG" and new_exchange_rate != Decimal("1"):
        raise ValueError("PYG journal entries must use an exchange_rate of exactly 1")

    for field, value in values.items():
        setattr(journal_entry, field, value)
    if "exchange_rate" in values:
        for line in journal_entry.lines:
            line.functional_debit = _money(line.debit * journal_entry.exchange_rate)
            line.functional_credit = _money(line.credit * journal_entry.exchange_rate)
    await session.commit()
    return await get_journal_entry(session, journal_entry_id)


async def delete_journal_entry(session: AsyncSession, journal_entry_id: UUID) -> bool:
    journal_entry = await get_journal_entry(session, journal_entry_id)
    if journal_entry is None:
        return False
    _assert_draft(journal_entry)
    await session.delete(journal_entry)
    await session.commit()
    return True


async def get_journal_line(session: AsyncSession, journal_line_id: UUID) -> JournalLine | None:
    return await session.get(JournalLine, journal_line_id)


async def add_journal_line(
    session: AsyncSession, journal_entry_id: UUID, data: JournalLineCreate
) -> JournalLine | None:
    journal_entry = await get_journal_entry(session, journal_entry_id)
    if journal_entry is None:
        return None
    _assert_draft(journal_entry)
    values = await _line_values(session, data=data, exchange_rate=journal_entry.exchange_rate)
    journal_line = JournalLine(
        journal_entry_id=journal_entry.id,
        line_number=await _next_line_number(session, journal_entry.id),
        **values,
    )
    session.add(journal_line)
    await session.commit()
    await session.refresh(journal_line)
    return journal_line


async def update_journal_line(
    session: AsyncSession, journal_line_id: UUID, data: JournalLineUpdate
) -> JournalLine | None:
    journal_line = await get_journal_line(session, journal_line_id)
    if journal_line is None:
        return None
    journal_entry = await get_journal_entry(session, journal_line.journal_entry_id)
    if journal_entry is None:
        raise RelatedResourceNotFoundError("journal entry")
    _assert_draft(journal_entry)
    values = await _line_values(
        session,
        data=data,
        exchange_rate=journal_entry.exchange_rate,
        existing=journal_line,
    )
    for field, value in values.items():
        setattr(journal_line, field, value)
    await session.commit()
    await session.refresh(journal_line)
    return journal_line


async def delete_journal_line(session: AsyncSession, journal_line_id: UUID) -> bool:
    journal_line = await get_journal_line(session, journal_line_id)
    if journal_line is None:
        return False
    journal_entry = await get_journal_entry(session, journal_line.journal_entry_id)
    if journal_entry is None:
        raise RelatedResourceNotFoundError("journal entry")
    _assert_draft(journal_entry)
    await session.delete(journal_line)
    await session.commit()
    return True


async def submit_journal_entry(
    session: AsyncSession, journal_entry_id: UUID
) -> JournalEntry | None:
    journal_entry = await get_journal_entry(session, journal_entry_id)
    if journal_entry is None:
        return None
    if journal_entry.status != "DRAFT":
        raise JournalEntryStateError("only DRAFT journal entries can be submitted for approval")
    _require_balanced_entry(journal_entry)
    await _require_postable_line_accounts(session, journal_entry)
    journal_entry.status = "PENDING_APPROVAL"
    await session.commit()
    return await get_journal_entry(session, journal_entry_id)


async def post_journal_entry(
    session: AsyncSession, journal_entry_id: UUID, data: JournalEntryPost
) -> JournalEntry | None:
    journal_entry = await get_journal_entry(session, journal_entry_id)
    if journal_entry is None:
        return None
    if journal_entry.status != "PENDING_APPROVAL":
        raise JournalEntryStateError(
            "only PENDING_APPROVAL journal entries can be posted"
        )
    if data.approved_by_actor == journal_entry.created_by_actor:
        raise ValueError("the journal entry creator cannot approve the same entry")
    _require_balanced_entry(journal_entry)
    await _require_postable_line_accounts(session, journal_entry)
    journal_entry.posted_at = datetime.now(timezone.utc)
    journal_entry.posted_by_actor = data.approved_by_actor
    journal_entry.posted_by_role = data.approved_by_role
    journal_entry.status = "POSTED"
    await session.commit()
    return await get_journal_entry(session, journal_entry_id)
