# Alembic Migrations

`20260914_0001` is intentionally domain-empty: it only creates PostgreSQL schemas
`core` and `shell` for one isolated customer database.

`20260915_0002` is the first business migration. It creates the canonical Core
entities `partner`, `account`, `tax`, `product`, `document`, and `document_item`
in the `core` schema. It uses the shared exact numeric types from
`app.core.financial_types` for every monetary amount, quantity, exchange rate,
and tax rate.

`20260915_0003` creates `journal_entry` and `journal_line`. It uses deferred
PostgreSQL constraint triggers to reject a posted entry unless its transaction-
and functional-currency debits equal credits, and database triggers to make
posted headers and lines immutable.

`20260915_0004` creates `core.outbox_event` for PostgreSQL transactional
outbox delivery. It stores immutable event identity, type/version, aggregate,
correlation, idempotency, and JSONB payload facts alongside publisher-owned
delivery state. A partial index supports pending-event retrieval and a database
trigger protects immutable event facts and valid delivery-state transitions.
