# ADR 0005: PostgreSQL Transactional Outbox

**Status:** ACCEPTED
**Date:** 2026-09-14

## Context

Critical workflows must notify adapters in real time, yet external networks and
provider services can fail. A user retry after a disconnection must not create a
second financial transaction.

## Decision

The Core uses a PostgreSQL transactional outbox from the first implementation.
The financial state change and its `outbox_event` are committed in the same
database transaction. A dedicated publisher delivers pending events to adapters
immediately after commit and persists attempt, delivery, and failure state.

Events carry an immutable event ID, event type and version, aggregate reference,
correlation ID, idempotency key, payload, and timestamps. Adapter requests are
authenticated and signed. Adapters must consume events idempotently.

Delivery is at-least-once; exactly-once processing across a network boundary is
not assumed. Retries use bounded backoff and failures become visible for recovery.
Adapter polling of the Core is permitted only for recovery, never as the normal
critical-workflow path.

Redis is not part of the MVP. It may be introduced later for cache, rate limiting,
or non-financial asynchronous workloads, but not as a replacement for the
transactional outbox.

## Consequences

- A committed purchase cannot lose its required integration event.
- Core and adapters remain independently deployable.
- Event consumers need idempotency tests from their first implementation.
