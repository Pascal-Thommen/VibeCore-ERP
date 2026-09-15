"""Pydantic contracts for the protected double-entry accounting core."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from app.schemas.core_schemas import (
    CoreReadSchema,
    CoreSchema,
    CurrencyCode,
    ExchangeRate,
    Money,
)

JournalEntryStatus = Literal["DRAFT", "PENDING_APPROVAL", "POSTED"]
ApprovalRole = Literal["ADMIN", "ACCOUNTANT"]
Actor = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]
EntryDescription = Annotated[
    str, StringConstraints(strict=True, min_length=1, max_length=2_000)
]
LineDescription = Annotated[str | None, StringConstraints(strict=True, max_length=500)]
Reference = Annotated[str | None, StringConstraints(strict=True, max_length=100)]


def _validate_line_sides(debit: Decimal, credit: Decimal) -> None:
    if (debit > 0) == (credit > 0):
        raise ValueError("a journal line must have exactly one positive debit or credit amount")


class JournalLineCreate(CoreSchema):
    account_id: UUID
    description: LineDescription = None
    debit: Money = Decimal("0")
    credit: Money = Decimal("0")

    @model_validator(mode="after")
    def validate_single_side(self) -> JournalLineCreate:
        _validate_line_sides(self.debit, self.credit)
        return self


class JournalLineUpdate(CoreSchema):
    """Mutable DRAFT line fields.

    When either amount is supplied on its own, the CRUD layer combines it with
    the existing line before checking the single-side constraint.
    """

    account_id: UUID | None = None
    description: LineDescription = None
    debit: Money | None = None
    credit: Money | None = None

    @model_validator(mode="after")
    def validate_complete_single_side(self) -> JournalLineUpdate:
        for field_name in ("account_id", "debit", "credit"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        if self.debit is not None and self.credit is not None:
            _validate_line_sides(self.debit, self.credit)
        return self


class JournalLineRead(CoreReadSchema):
    journal_entry_id: UUID
    line_number: int
    account_id: UUID
    description: str | None
    debit: Decimal
    credit: Decimal
    functional_debit: Decimal
    functional_credit: Decimal


class JournalEntryCreate(CoreSchema):
    created_by_actor: Actor
    entry_date: date
    description: EntryDescription
    reference: Reference = None
    source_document_id: UUID | None = None
    reverses_entry_id: UUID | None = None
    currency_code: CurrencyCode
    functional_currency_code: Literal["PYG"] = "PYG"
    exchange_rate: ExchangeRate = Decimal("1")
    lines: list[JournalLineCreate] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_balanced_entry(self) -> JournalEntryCreate:
        if not self.description.strip():
            raise ValueError("description must not be blank")
        if self.currency_code == "PYG" and self.exchange_rate != Decimal("1"):
            raise ValueError("PYG journal entries must use an exchange_rate of exactly 1")
        debit_total = sum((line.debit for line in self.lines), Decimal("0"))
        credit_total = sum((line.credit for line in self.lines), Decimal("0"))
        if debit_total != credit_total:
            raise ValueError("journal entry debit and credit totals must be equal")
        return self


class JournalEntryUpdate(CoreSchema):
    """Only mutable DRAFT header fields; status and posting facts are excluded."""

    entry_date: date | None = None
    description: Annotated[
        str | None, StringConstraints(strict=True, min_length=1, max_length=2_000)
    ] = None
    reference: Reference = None
    source_document_id: UUID | None = None
    currency_code: CurrencyCode | None = None
    functional_currency_code: Literal["PYG"] | None = None
    exchange_rate: ExchangeRate | None = None

    @model_validator(mode="after")
    def validate_description(self) -> JournalEntryUpdate:
        for field_name in (
            "entry_date",
            "description",
            "currency_code",
            "functional_currency_code",
            "exchange_rate",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        if self.description is not None and not self.description.strip():
            raise ValueError("description must not be blank")
        return self


class JournalEntryPost(CoreSchema):
    """Approval actor captured when a pending entry is posted."""

    approved_by_actor: Actor
    approved_by_role: ApprovalRole

    @model_validator(mode="after")
    def validate_human_actor(self) -> JournalEntryPost:
        if self.approved_by_actor in {"AI_AGENT", "SYSTEM_AGENT"}:
            raise ValueError("AI_AGENT and SYSTEM_AGENT cannot approve journal entries")
        return self


class JournalEntryRead(CoreReadSchema):
    status: JournalEntryStatus
    created_by_actor: str
    entry_date: date
    description: str
    reference: str | None
    source_document_id: UUID | None
    reverses_entry_id: UUID | None
    currency_code: CurrencyCode
    functional_currency_code: CurrencyCode
    exchange_rate: Decimal
    posted_at: datetime | None
    posted_by_actor: str | None
    posted_by_role: ApprovalRole | None
    lines: list[JournalLineRead]
