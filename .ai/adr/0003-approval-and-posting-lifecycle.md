# ADR 0003: Four-Eyes Approval and Immutable Posting Lifecycle

**Status:** ACCEPTED
**Date:** 2026-09-14

## Context

AI assistance and intermittent connectivity must never create unreviewed or
duplicate financial postings. Posted ledger data must remain auditable.

## Decision

The initial lifecycle is:

```text
DRAFT → PENDING_APPROVAL → POSTED
```

- `DRAFT` is editable. It may be created by a human, system, or AI agent.
- `PENDING_APPROVAL` is frozen for the creator and awaits a human decision.
- `POSTED` is immutable and cannot be edited or deleted.

The Core enforces a four-eyes rule: the human who approves a draft must not be
the draft's creator. `AI_AGENT` and `SYSTEM_AGENT` can never approve financial
transactions. Eligible roles are defined by Core authorization policy.

An error in a posted entry is corrected only by posting a separate balanced
reversing entry. The original record remains intact; it may be shown as
`REVERSED` only when linked to that posted reversing entry. `REVERSED` is not an
editable transition and never mutates the original debit or credit lines.

Every transition writes an immutable audit record with actor, timestamp,
correlation ID, and reason where applicable.

## Consequences

- The MVP has a predictable approval model.
- More elaborate client-specific approval chains may be added in the Shell later,
  but cannot weaken Core posting and separation-of-duties guarantees.
