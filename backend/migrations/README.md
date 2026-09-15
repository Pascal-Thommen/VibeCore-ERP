# Alembic Migrations

`20260914_0001` is intentionally domain-empty: it only creates PostgreSQL schemas
`core` and `shell` for one isolated customer database.

`20260915_0002` is the first business migration. It creates the canonical Core
entities `partner`, `account`, `tax`, `product`, `document`, and `document_item`
in the `core` schema. It uses the shared exact numeric types from
`app.core.financial_types` for every monetary amount, quantity, exchange rate,
and tax rate.
