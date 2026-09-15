from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.db.base import CORE_SCHEMA
from app.main import app
from app.models import JournalEntry, JournalLine
from app.schemas.accounting_schemas import JournalEntryCreate, JournalEntryPost, JournalLineUpdate


@pytest.fixture
def journal_entry_payload() -> dict[str, object]:
    return {
        "created_by_actor": "AI_AGENT",
        "entry_date": "2026-09-15",
        "description": "Initial cash sale",
        "currency_code": "PYG",
        "lines": [
            {
                "account_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "debit": "100000",
                "credit": "0",
            },
            {
                "account_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "debit": "0",
                "credit": "100000",
            },
        ],
    }


def test_journal_models_use_protected_core_schema_and_exact_numeric_amounts() -> None:
    assert JournalEntry.__table__.schema == CORE_SCHEMA
    assert JournalLine.__table__.schema == CORE_SCHEMA
    assert JournalEntry.__table__.name == "journal_entry"
    assert JournalLine.__table__.name == "journal_line"

    for column_name in ("debit", "credit", "functional_debit", "functional_credit"):
        amount = JournalLine.__table__.c[column_name].type
        assert amount.precision == 20
        assert amount.scale == 6

    constraints = {constraint.name for constraint in JournalLine.__table__.constraints}
    assert "ck_journal_line_exactly_one_transaction_side" in constraints
    assert "ck_journal_line_exactly_one_functional_side" in constraints


def test_journal_entry_schema_requires_balanced_decimal_lines(
    journal_entry_payload: dict[str, object],
) -> None:
    entry = JournalEntryCreate.model_validate(journal_entry_payload)
    assert entry.exchange_rate == 1

    unbalanced = deepcopy(journal_entry_payload)
    unbalanced["lines"] = [
        *unbalanced["lines"][:-1],  # type: ignore[index]
        {
            "account_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "debit": "0",
            "credit": "99999",
        },
    ]
    with pytest.raises(ValidationError, match="debit and credit totals must be equal"):
        JournalEntryCreate.model_validate(unbalanced)

    float_amount = deepcopy(journal_entry_payload)
    float_amount["lines"] = [
        {
            "account_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "debit": 100000.0,
            "credit": "0",
        },
        {
            "account_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "debit": "0",
            "credit": "100000",
        },
    ]
    with pytest.raises(ValidationError, match="never floats"):
        JournalEntryCreate.model_validate(float_amount)


def test_journal_posting_schema_requires_a_human_approver() -> None:
    with pytest.raises(ValidationError, match="cannot approve"):
        JournalEntryPost.model_validate(
            {"approved_by_actor": "AI_AGENT", "approved_by_role": "ACCOUNTANT"}
        )

    with pytest.raises(ValidationError):
        JournalEntryPost.model_validate(
            {"approved_by_actor": "eligible-user", "approved_by_role": "SYSTEM_AGENT"}
        )


def test_journal_line_update_cannot_null_out_posting_amounts() -> None:
    with pytest.raises(ValidationError, match="debit cannot be null"):
        JournalLineUpdate.model_validate({"debit": None})


def test_journal_routes_and_database_invariants_are_registered() -> None:
    paths = {route.path for route in app.routes}
    assert "/api/v1/journal-entries" in paths
    assert "/api/v1/journal-entries/{journal_entry_id}/post" in paths

    migration = Path("migrations/versions/20260915_0003_create_double_entry_accounting.py")
    migration_source = migration.read_text()
    assert "CREATE CONSTRAINT TRIGGER journal_entry_posted_balance" in migration_source
    assert "CREATE TRIGGER journal_entry_lifecycle_guard" in migration_source
    assert "CREATE TRIGGER journal_line_posted_immutability_guard" in migration_source
