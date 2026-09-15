# Alembic Migrations

`20260914_0001` is intentionally domain-empty: it only creates PostgreSQL schemas
`core` and `shell` for one isolated customer database.

The next migration introduces canonical Core entities. It must use exact numeric
types from `app.core.financial_types` for every financial amount, quantity, and
exchange rate.
