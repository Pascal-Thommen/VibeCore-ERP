# Architecture Decision Records

Each ADR records a durable architectural decision, its context, and its
consequences. ADRs are written in English and use this lifecycle:

- `PROPOSED` — under review; not binding.
- `ACCEPTED` — binding for new implementation.
- `SUPERSEDED` — retained as history and replaced by a named ADR.

Do not change the outcome of an accepted ADR. Create a new ADR that explicitly
supersedes it instead.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-single-tenant-deployment.md) | Isolated deployment per customer | ACCEPTED |
| [0002](0002-finance-core-and-ledger-boundary.md) | Protected financial core and canonical MVP model | ACCEPTED |
| [0003](0003-approval-and-posting-lifecycle.md) | Four-eyes approval and immutable posting | ACCEPTED |
| [0004](0004-authentication-secrets-and-service-trust.md) | JWT, service trust, and secret handling | ACCEPTED |
| [0005](0005-postgresql-transactional-outbox.md) | PostgreSQL transactional outbox | ACCEPTED |
| [0006](0006-supplier-purchase-reference-module.md) | Raw-material supplier purchase as reference workflow | ACCEPTED |
| [0007](0007-sifen-adapter-boundary-and-rollout.md) | SIFEN boundary and staged rollout | ACCEPTED |
| [0008](0008-library-and-implementation-policy.md) | Mature-library policy | ACCEPTED |
