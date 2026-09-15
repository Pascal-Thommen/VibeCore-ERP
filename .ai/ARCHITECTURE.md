# VibeCore ERP — Binding Architecture Contract

**Status:** Active
**Applies to:** Every contributor, service, and AI agent in this repository

VibeCore ERP is a headless, composable financial foundation for client-specific
ERP systems. The Finance Core protects financial truth. The Shell models the
client's actual operational workflow. Adapters isolate external providers.

## Non-negotiable constraints

- One customer is one isolated deployment and one dedicated PostgreSQL database.
- The database uses the protected `core` schema and the extensible `shell` schema.
- The Finance Core uses Python, FastAPI, PostgreSQL, SQLAlchemy, Pydantic, and
  Alembic. Use established libraries; do not recreate commodity infrastructure.
- The `core` schema may only change through explicit architecture-owner approval
  and a deterministic, reviewed Alembic migration.
- Adapters never receive direct database connectivity or database credentials.
- Core-to-adapter payloads use versioned JSON over authenticated REST and events.
- Critical external actions are event-driven in real time. Polling is recovery only.
- Financial records proposed by an AI agent are `DRAFT` until an eligible human
  approves them. Posted records are never edited or deleted.
- All money and exchange rates use PostgreSQL exact `NUMERIC` values. Floating
  point values are forbidden for financial calculations.
- Every cross-boundary JSON payload supports optional `meta` and `custom_data`
  objects for compatible evolution.
- Every adapter exposes `openapi.json` and maintains `.ai/adapter_schema.md`.

## Paraguay implementation boundary

VibeCore-PY natively models RUC, partner fiscal identity, IVA classification,
Timbrado references, and SIFEN result facts. The SIFEN adapter alone owns XML/
SOAP mapping, certificate handling, signing, transmission, and provider retries.

## Decision records

The current decisions are in [adr/](adr). New decisions that alter a durable
boundary must be recorded as a new ADR before implementation begins.
