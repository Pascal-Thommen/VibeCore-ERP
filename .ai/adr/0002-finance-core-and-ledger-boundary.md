# ADR 0002: Protected Finance Core and Canonical MVP Model

**Status:** ACCEPTED
**Date:** 2026-09-14

## Context

The reusable financial foundation must be strict enough for accounting and tax
integrity while allowing every customer to have an individual operational Shell.

## Decision

The Core MVP owns these canonical entities:

- `company`
- `fiscal_period`
- `account`
- `tax_rate`
- `partner`
- `journal_entry`
- `journal_line`
- `approval`
- `audit_log`
- `outbox_event`

`partner` is a Core entity. Its legal name and RUC are fiscal facts and provide
the canonical customer/supplier identity for ledger and SIFEN references.

The Core records double-entry accounting, fiscal periods, tax classification,
financial approvals, audit history, and integration events. The Shell records
client-specific operational data, such as scale readings, tare weight, gross
weight, and intake workflows. Shell records may reference Core primary keys;
they may not bypass Core accounting rules.

PYG is the functional currency. Every financial record is multi-currency-ready
from the first migration: it preserves transaction currency, functional currency,
the exact exchange-rate snapshot, and functional-currency amounts. The MVP may
post PYG-only transactions and does not yet implement currency revaluation.

All monetary values and exchange rates use exact PostgreSQL `NUMERIC` types and
application-level decimal arithmetic. IEEE floating-point arithmetic is forbidden
for financial calculations.

## Consequences

- Import and foreign-currency support can be added without redesigning posted
  ledger records.
- Financial data is reusable across client-specific Shells.
- Core changes are high-governance changes and require reviewed migrations.
