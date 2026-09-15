# ADR 0006: Raw-Material Supplier Purchase as the Reference Module

**Status:** ACCEPTED
**Date:** 2026-09-14

## Context

The first vertical slice must validate Core accounting, an individual Shell
workflow, approval, tax, cash/payables, and external-event behavior together.

## Decision

The first Vibe Shell reference module is a supplier purchase of raw materials,
such as maize, captured through a scale workflow.

The Shell captures the supplier, gross weight, tare weight, net weight, quality
or pricing inputs, and payment choice. Scale-specific data belongs to the `shell`
schema. The Shell sends an idempotent purchase request to the Core. The Core
creates a `DRAFT` journal entry, applies IVA treatment, and records the financial
counterparty through `core.partner`.

After a different eligible human approves it, the Core atomically posts a balanced
cash or accounts-payable entry, writes the audit trail, and creates the required
outbox event. The workflow is the reference implementation for later modules.

## Consequences

- We validate the architecture against a real physical process before expanding
  generic module coverage.
- The Core remains free of weighing-specific tables and UI logic.
