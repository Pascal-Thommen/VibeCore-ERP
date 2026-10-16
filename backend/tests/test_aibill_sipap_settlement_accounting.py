"""
Tests verifying VibeCore ERP schema validation and SDK client operations
for AIBill Monthly Value Pool Settlement and SIPAP Developer Payout Accounting.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

# Ensure SDK is importable
sdk_path = Path(__file__).resolve().parents[2] / "sdk"
if str(sdk_path) not in sys.path:
    sys.path.insert(0, str(sdk_path))

from vibecore.client import CoreClient  # noqa: E402

from app.schemas.accounting_schemas import JournalEntryCreate  # noqa: E402


def test_aibill_developer_pool_accrual_schema_validation() -> None:
    """
    Validates Deliverable 2:
    Soll: Aufwand Entwickler-Pool
    Haben: Verbindlichkeiten gegenueber Entwicklern (verteilt auf Entwickler)
    """
    expense_account_id = uuid4()
    dev_a_liability_account_id = uuid4()
    dev_b_liability_account_id = uuid4()

    payload = {
        "created_by_actor": "AIBILL_SYSTEM",
        "entry_date": "2026-10-31",
        "description": "AIBill Monatsabrechnung 2026-10: Erfolgsbeteiligung 50/50 Net Value Pool",
        "reference": "POOL-2026-10",
        "currency_code": "PYG",
        "functional_currency_code": "PYG",
        "exchange_rate": 1,
        "lines": [
            {
                "account_id": expense_account_id,
                "description": "Aufwand Entwickler-Pool Erfolgsbeteiligung 2026-10",
                "debit": "127687.500000",
                "credit": "0",
            },
            {
                "account_id": dev_a_liability_account_id,
                "description": "Verbindlichkeit Pool-Anteil Entwickler Carlos Martinez (2026-10)",
                "debit": "0",
                "credit": "95765.625000",
            },
            {
                "account_id": dev_b_liability_account_id,
                "description": "Verbindlichkeit Pool-Anteil Entwickler Maria Benitez (2026-10)",
                "debit": "0",
                "credit": "31921.875000",
            },
        ],
    }

    entry = JournalEntryCreate.model_validate(payload)
    assert entry.currency_code == "PYG"
    assert entry.exchange_rate == Decimal("1")
    assert entry.reference == "POOL-2026-10"
    assert len(entry.lines) == 3

    # Total debits equal total credits
    total_debit = sum(line.debit for line in entry.lines)
    total_credit = sum(line.credit for line in entry.lines)
    assert total_debit == total_credit == Decimal("127687.500000")


def test_aibill_sipap_bank_payout_schema_validation_and_reference() -> None:
    """
    Validates Deliverables 3 & 4:
    Soll: Verbindlichkeiten gegenueber Entwicklern (entlastet Verbindlichkeit)
    Haben: Bank (SIPAP Ueberweisungskonto)
    Protokolliert die SIPAP-Banktransaktions-Referenz lueckenlos.
    """
    dev_liability_account_id = uuid4()
    sipap_bank_account_id = uuid4()
    sipap_reference = "SIPAP-20261031-DEV001-9F2B8A"

    payload = {
        "created_by_actor": "AIBILL_SYSTEM",
        "entry_date": "2026-11-01",
        "description": f"SIPAP Entwicklerauszahlung an Carlos Martinez - Ref: {sipap_reference}",
        "reference": sipap_reference,
        "currency_code": "PYG",
        "functional_currency_code": "PYG",
        "exchange_rate": 1,
        "lines": [
            {
                "account_id": dev_liability_account_id,
                "description": (
                    f"Entlastung Verbindlichkeit via SIPAP Ref {sipap_reference} "
                    "fuer Carlos Martinez"
                ),
                "debit": "95765.625000",
                "credit": "0",
            },
            {
                "account_id": sipap_bank_account_id,
                "description": (
                    f"Bankabgang SIPAP Ueberweisung Ref {sipap_reference} an Carlos Martinez"
                ),
                "debit": "0",
                "credit": "95765.625000",
            },
        ],
    }

    entry = JournalEntryCreate.model_validate(payload)
    assert entry.reference == sipap_reference
    assert len(entry.lines) == 2

    # Liability line is debit (entlastet die Verbindlichkeit)
    assert entry.lines[0].debit == Decimal("95765.625000")
    assert entry.lines[0].credit == Decimal("0")

    # Bank line is credit (Bankabgang)
    assert entry.lines[1].credit == Decimal("95765.625000")
    assert entry.lines[1].debit == Decimal("0")


def test_aibill_sipap_bank_payout_with_10_percent_retencion_autofactura_schema_validation() -> None:
    """
    Validates Autofactura with 10% Retencion for developers without RUC under Ley 6380/19:
    Soll: Verbindlichkeiten gegenueber Entwicklern (100% = 100.000 Gs)
    Haben: Bank SIPAP Ueberweisungskonto (90% = 90.000 Gs)
    Haben: Verbindlichkeit Steueramt DNIT / Retenciones por Pagar (10% = 10.000 Gs)
    """
    dev_liability_account_id = uuid4()
    sipap_bank_account_id = uuid4()
    dnit_retention_account_id = uuid4()
    sipap_reference = "SIPAP-20261031-DEV002-3C7E1A"
    autofactura_doc = "AF-202610-A1B2C3"

    payload = {
        "created_by_actor": "AIBILL_SYSTEM",
        "entry_date": "2026-11-01",
        "description": (
            f"SIPAP Entwicklerauszahlung an Maria Benitez / Ref: {sipap_reference} "
            f"[Autofactura {autofactura_doc} mit 10% Retencion]"
        ),
        "reference": sipap_reference,
        "currency_code": "PYG",
        "functional_currency_code": "PYG",
        "exchange_rate": 1,
        "lines": [
            {
                "account_id": dev_liability_account_id,
                "description": (
                    f"Entlastung Verbindlichkeit via SIPAP Ref {sipap_reference} "
                    "fuer Maria Benitez"
                ),
                "debit": "100000.000000",
                "credit": "0",
            },
            {
                "account_id": sipap_bank_account_id,
                "description": (
                    f"Bankabgang SIPAP Ueberweisung (90%) Ref {sipap_reference} an Maria Benitez"
                ),
                "debit": "0",
                "credit": "90000.000000",
            },
            {
                "account_id": dnit_retention_account_id,
                "description": (
                    "Steuereinbehalt 10% DNIT Retenciones por Pagar fuer Maria Benitez "
                    f"Autofactura {autofactura_doc}"
                ),
                "debit": "0",
                "credit": "10000.000000",
            },
        ],
    }

    entry = JournalEntryCreate.model_validate(payload)
    assert entry.reference == sipap_reference
    assert len(entry.lines) == 3

    total_debit = sum(line.debit for line in entry.lines)
    total_credit = sum(line.credit for line in entry.lines)
    assert total_debit == total_credit == Decimal("100000.000000")

    # Line 1: 100% debit on liabilities
    assert entry.lines[0].debit == Decimal("100000.000000")
    assert entry.lines[0].credit == Decimal("0")

    # Line 2: 90% credit on bank
    assert entry.lines[1].credit == Decimal("90000.000000")
    assert entry.lines[1].debit == Decimal("0")

    # Line 3: 10% credit on DNIT retenciones
    assert entry.lines[2].credit == Decimal("10000.000000")
    assert entry.lines[2].debit == Decimal("0")


def test_core_client_sdk_has_accounting_methods() -> None:
    """Verifies that vibecore.client.CoreClient exposes accounting methods."""
    client = CoreClient("http://localhost:8000", access_token="test-token")
    assert hasattr(client, "create_account")
    assert hasattr(client, "get_account")
    assert hasattr(client, "list_accounts")
    assert hasattr(client, "create_journal_entry")
    assert hasattr(client, "get_journal_entry")
    assert hasattr(client, "list_journal_entries")
    assert hasattr(client, "post_journal_entry")
    client.close()

