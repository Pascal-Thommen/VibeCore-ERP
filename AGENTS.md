# VibeCore ERP Agent Instructions

Read [.ai/ARCHITECTURE.md](.ai/ARCHITECTURE.md) and the applicable ADRs in
[.ai/adr](.ai/adr) before proposing or implementing a change.

These instructions are binding for humans and AI agents:

1. The `core` schema is protected. Do not change it without explicit
   architecture-owner approval and a reviewed migration.
2. Adapters never access PostgreSQL directly; they use authenticated APIs and
   events only.
3. Shell schema changes require deterministic Alembic migrations.
4. Financial work created by AI remains `DRAFT` until an eligible human approves it.
5. Never implement custom cryptography, hashing, XML-signing, or transport
   protocols where an established library exists.

When an ADR conflicts with a README or implementation convenience, the ADR wins.
