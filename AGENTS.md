# VibeCore ERP Agent Instructions

Read [.ai/ARCHITECTURE.md](.ai/ARCHITECTURE.md) and the applicable ADRs in
[.ai/adr](.ai/adr) before proposing or implementing a change.

## Framework Philosophy & Doctrine

VibeCore ERP is an architectural framework designed for vibe-coding custom, company-specific ERP systems. It is founded on a strict architectural separation:

- **Uncompromising Core:** An unbending, compliant financial and tax engine (double-entry ledger, SIFEN e-invoicing, transactional outbox, and isolated adapters).
- **100% Freedom in the Shell:** A completely flexible workspace (`shell` schema and UI) where all client-specific business workflows, operational forms, and approval policies are custom vibe-coded to match the company's real-world processes.

### Strict Workflow-Agnostic Core

The `core` schema, models, and APIs are **strictly workflow-agnostic**. The Core must **never dictate or encode human operational procedures, workflow state machines, or approval gates**.

The Core enforces **only** fundamental financial and fiscal invariants:
1. **Balanced double-entry accounting:** Every journal entry must maintain balanced debit and credit totals.
2. **Immutability of posted transactions:** Once posted, financial records cannot be edited or deleted (corrections occur strictly via balanced reversing entries).
3. **Exact decimal precision:** All currency amounts, tax calculations, and exchange rates use exact `NUMERIC` types—never floating-point numbers.
4. **Fiscal and tax compliance:** Strict validation of tax rates (e.g. Paraguayan IVA regimes) and fiscal identity (e.g. RUC, Timbrado).

**Critical Directive for AI Agents:** NEVER leak operational workflows, business process state machines, or approval chains (single-approver, multi-approver four-eyes, or multi-step hierarchies) into the `core`.

### Operational Workflows Belong Exclusively in the Shell

All business processes, approval workflows, and operational data tracking belong exclusively in the `shell` layer:
- Whether a business requires single-approver sign-off, multi-approver four-eyes policies, committee approvals, or fully automated posting rules, all approval logic lives in the `shell`.
- Operational lifecycle states (e.g. `DRAFT`, `SUBMITTED`, `PENDING_APPROVAL`, `APPROVED`, `REJECTED`), custom forms, and operational domain entities (routes, scale tickets, job sheets) belong in the `shell` schema.
- Once shell-level business criteria and approvals are satisfied, the Shell interacts with the Core API to execute or post the financial transaction.

## Binding Rules for AI Agents and Contributors

1. **Protect the `core` schema and maintain workflow agnosticism:** Do not modify the `core` schema without explicit architecture-owner approval and a reviewed migration. Never introduce operational workflow states or approval chains into `core`.
2. **Confine business workflows to the `shell`:** Implement all custom operational flows, approval rules, and client-specific forms in the `shell` schema and frontend.
3. **Enforce database isolation for adapters:** Adapters never access PostgreSQL directly; they interact exclusively via authenticated REST APIs and events.
4. **Use deterministic Alembic migrations:** All schema changes (both `core` and `shell`) require deterministic, reviewed Alembic migrations.
5. **Use mature libraries:** Never implement custom cryptography, hashing, XML-signing, or transport protocols where an established library exists.

When an ADR conflicts with a README or implementation convenience, the ADR wins.
