# VibeCore ERP

> **A composable, AI-first ERP foundation for SMEs — built around the way a business actually works.**

VibeCore ERP is an architectural framework designed for vibe-coding custom, company-specific ERP systems. It provides an unbending, compliant financial and tax core while leaving all business workflows, approval policies, and operational processes to be custom vibe-coded inside each company's individual `shell` layer.

Instead of repeatedly rebuilding generic CRUD applications or forcing companies into rigid standard ERP workflows, VibeCore establishes a clear architectural separation:
- **Uncompromising Core (Finance, Tax, Outbox, Adapters):** Strictly workflow-agnostic. Enforces financial invariants (balanced debit/credit, immutability of posted transactions, exact currency precision) and regulatory compliance.
- **100% Freedom in the Shell (Vibe-coded processes):** Complete freedom to vibe-code bespoke business workflows, operational forms, and custom approval policies (single-approver, multi-approver, or automated) that reflect how each business actually operates.

**Core principle:** the business process shapes the software — never the other way around.

> Accepted ADRs and `AGENTS.md` are binding. They take precedence if this README
> ever conflicts with them.

## Why VibeCore?

Traditional ERPs force every company into the same screens, modules, and processes. VibeCore takes the opposite approach:

- **Finance stays reliable.** Double-entry accounting, tax logic, and financial
  integrity live in one protected, workflow-agnostic core.
- **The client experience stays flexible.** 100% freedom in the shell: each business gets
  a shell that matches its real operations: a scale at a gold buyer, a counter at a store,
  or a mobile workflow in the field.
- **Integrations stay replaceable.** WhatsApp, e-invoicing, banking, OCR, and
  future services run outside the core as isolated adapters.
- **Vibe-coded workflows with custom governance.** AI agents vibe-code business processes
  and approval policies directly into the shell layer. Whether a company requires single-approver
  sign-off, four-eyes validation, or automated autonomous processing, the business dictates
  the policy in the shell while the Core guarantees accounting and tax truth.

VibeCore is designed for micro, small, and medium-sized enterprises (MSMEs), especially teams that need bespoke operational software without bespoke financial foundations every time.

## Architecture at a glance

```mermaid
flowchart LR
  U[Client-specific UI\nFlexible Vibe Shell] -->|REST / JSON| C
  U -->|REST / JSON| S

  C[Immutable Finance Core\nFastAPI + PostgreSQL]
  S[Client-specific Shell API\nOperational workflows]

  C -->|real-time events / webhooks| A1[SIFEN adapter\nCore-bound]
  C -->|real-time events / webhooks| A3[Banking adapter\nCore-bound]
  S -->|operational events / webhooks| A2[WhatsApp, IoT, notifications\nShell-bound]

  A1 -->|authenticated REST / JSON| C
  A2 -->|authenticated REST / JSON| S
  A3 -->|authenticated REST / JSON| C

  subgraph PostgreSQL
    C1[core schema\nprotected financial truth]
    S1[shell schema\nclient workspace]
  end

  C --- C1
  S --- S1
```

| Layer | Responsibility | Freedom to change |
| --- | --- | --- |
| **Finance Core** (`/backend`) | Accounting, items, taxes, transaction integrity | Protected |
| **Shell workspace** (`shell` schema) | Client-specific processes, data, and UI | Extensible |
| **Adapters** | External services and provider-specific logic | Isolated and replaceable |
| **Vibe Shell** (`/frontend`) | Task-focused client interface | Fully open; choose the suitable stack |

## The two-tier standard

### VibeCore ERP — the global standard

The global architecture is deliberately portable:

- **Headless by design.** The Finance Core owns no user interface.
- **Process proximity.** Client workflows determine the Shell experience;
  standard ERP screens do not.
- **Prompt as code.** Define the model and contracts clearly; let AI generate
  the repetitive integration work.
- **Modern, minimal foundation.** The Core uses raw Python with FastAPI and
  PostgreSQL — no legacy ERP framework.

### VibeCore PY — the Paraguayan implementation

VibeCore-PY applies the global standard to Paraguay. Implementations in this context must:

- Use the Paraguayan Chart of Accounts under **Ley 6380/19**.
- Validate **RUC** values, including the check digit (**DV**).
- Prioritize a **SIFEN / e-Kuatia** adapter for electronic invoices.
- Support **Marangatú** export formats, including **RG 90** requirements.
- Model the three IVA treatments for every applicable financial transaction:
  **exempt, 5%, and 10%**.
- Build complex tax forms—such as IRE Form 500/501—as external localization
  services or modules. They query balances through the authenticated Core API;
  they are not Core code and never access PostgreSQL directly.

> Compliance is a product requirement, not an adapter detail. Local tax and
> e-invoicing rules must be independently reviewed and kept current before
> production use.

## Layer A — Immutable Finance Core

The Finance Core is one monolithic service and database boundary, chosen intentionally for ACID-safe financial transactions.

**Required stack:** Python, FastAPI, PostgreSQL.

**Hard one-way boundary:** The Core must **never** read from the Shell or depend
on it. The Core owns financial asset values; the Shell may own operational asset
tracking, such as locations, condition, or scans. Shell workflows can reference
Core records, but operational requirements must never become a dependency of
financial truth.

The `core` PostgreSQL schema is limited to the durable financial domain:

- Double-entry accounting
- Items and financial master data
- Tax calculation and classification
- Financial transaction state

### Core invariants

1. **The Core is strictly workflow-agnostic.** Operational business processes, approval chains, and workflow state machines belong exclusively in the Shell.
2. **AI agents must not modify the `core` schema** without explicit architecture-owner approval and a reviewed migration path.
3. Financial records must preserve balanced, auditable double-entry semantics.
4. Posted financial transactions are immutable; adjustments are made strictly via balanced reversing entries.
5. All monetary calculations and exchange rates must use exact `NUMERIC` types (never floating-point).
6. Every financial action records an `actor`, such as `HUMAN_CARLOS`, `SYSTEM_CRON`, or `AI_AGENT`.

The Core is intentionally small and workflow-agnostic. It guarantees financial and tax invariants, not the peculiarities or approval policies of an individual client’s operational workflow.

## The Shell workspace

The `shell` PostgreSQL schema is where a client’s actual business lives.

It may contain client-specific tables, views, and workflows — for example scale readings for a precious-metals buyer, delivery routes, service orders, or shop-floor data. Shell tables may reference Core primary keys through foreign keys, but must not redefine or bypass financial rules.

Every Shell schema change requires a deterministic Alembic migration. Migrations must be reproducible, reviewed, and safe to apply in a clean environment.

## Layer B — Adapters: Core-bound and Shell-bound

Adapters connect VibeCore to the outside world. They run as independent Dockerized microservices and are free to use the language and runtime that best suits the provider: Node.js, Go, Python, or another appropriate stack.

### Adapter topology

- **Core-bound adapters** — for example SIFEN and Banking — integrate with the
  Finance Core’s authenticated API and event boundary to handle compliance,
  invoices, and accounting triggers.
- **Shell-bound adapters** — for example WhatsApp, operational notifications,
  and IoT scale feeds — integrate with client-specific Shell workflows through
  authenticated Shell APIs and events.

### Adapter contract

- Communicate with the Core or Shell exclusively through versioned **JSON over
  authenticated REST APIs and events**.
- **Never connect directly to PostgreSQL.** Database isolation is absolute for
  both Core-bound and Shell-bound adapters.
- Expose an `openapi.json` specification.
- Include an AI-readable contract at `.ai/adapter_schema.md`.
- Include a `/blueprints` directory when the adapter needs reusable
  user-interface components, such as an OCR camera flow.
- Treat provider credentials, signing keys, and secrets as runtime
  configuration — never commit them.

### Real-time first, recovery second

Critical business actions must use real-time Core-to-Adapter or
Shell-to-Adapter events and webhooks. For example, a POS checkout that needs a
SIFEN e-invoice triggers the SIFEN adapter immediately.

An adapter may poll the relevant API only for recovery, such as reconciling
missed work after startup. Polling is **not** a substitute for a real-time
business workflow.

### VibeCore Python SDK

The `vibecore-sdk` gives AI agents and adapters a typed Python interface to the
authenticated Core API. It is the preferred Python integration boundary for
Core operations and never provides database access.

## Layer C — Flexible Vibe Shell frontend

The Vibe Shell is the client-facing layer. Vue or React with Tailwind CSS is a
common reference stack for web interfaces, but the architecture is fully open:
build the Shell with any framework or stack — such as Streamlit, custom Python
frontends, or native apps — that fits the workflow.

The Shell owns workflow design, visual identity, and task-specific interaction. It should make the client’s daily work feel native, while the Finance Core remains invisible and dependable underneath.

For complex integrations, adapter repositories should ship generic frontend
blueprints in `/blueprints`. AI agents can copy these components into the Shell
and tailor their styling and placement without reimplementing the integration
contract.

## Data, API, and MCP conventions

### Design for the next unknown requirement

Every JSON payload exchanged among the Core, Shell, and Adapters must provide
optional extension objects:

```json
{
  "id": "txn_01J...",
  "status": "DRAFT",
  "meta": {},
  "custom_data": {}
}
```

Use `meta` for interoperable technical or integration metadata. Use
`custom_data` for domain-specific extensions. Consumers must tolerate fields
they do not recognize. This keeps contracts forward-compatible without breaking
older clients.

### Flexible Core-table extensions

Flexible Core tables—such as `partner`, `product`, and `document` when present
in the canonical model—provide a JSONB extension column, for example `meta` or
`custom_data`. It holds future-proof, customer-specific attributes without
altering the protected `core` schema. These extension objects complement rather
than replace canonical fiscal and financial fields; a new protected field still
requires architecture-owner approval and a reviewed deterministic Alembic
migration.

### State, traceability, and Model Context Protocol (MCP)

- Record the actor responsible for every financial action.
- Preserve audit context and operational history in the Shell.
- Keep the Core workflow-agnostic; implement approval policies (human, multi-approver, or automated) in the Shell.
- Prefer explicit, idempotent API operations for event retries and recovery.
- **MCP integration:** AI developer agents interact through Model Context
  Protocol (MCP) servers that expose safe tools and resources. MCP servers use
  the same authenticated API boundaries as other integrations; they never
  receive direct database credentials and must preserve immutable Core barriers.

## Repository conventions

As modules are added, follow this structure:

```text
.
├── backend/                 # FastAPI Finance Core and Shell services
│   ├── core/                # Protected financial domain
│   └── shell/               # Client-specific workspace domain
├── sdk/                     # vibecore-sdk: typed Python client for the Core API
│   └── vibecore/
├── frontend/                # Flexible Vibe Shell (choice of stack)
├── adapters/                # Isolated Core-bound and Shell-bound services
│   └── <adapter>/
│       ├── .ai/adapter_schema.md
│       ├── blueprints/      # Optional reusable UI components
│       └── openapi.json
├── migrations/              # Deterministic Alembic migrations
└── docs/                    # Architecture decisions and operating guides
```

## Instructions for AI agents and contributors

Before implementing a feature, identify its layer.

| If you need to… | Build it in… |
| --- | --- |
| Post a journal entry, calculate tax, or enforce accounting rules | Finance Core |
| Capture a client-specific operational process or approval chain | Shell schema + Vibe Shell |
| Connect a third-party service | Core-bound or Shell-bound adapter |
| Implement custom business workflows, approvals, or operational forms | Shell schema + Vibe Shell |

Non-negotiable rules:

- Do not change the `core` schema without explicit architecture-owner approval and a reviewed migration.
- Do not leak operational workflows or approval chains into the `core`; keep the Core strictly workflow-agnostic.
- Do not give adapters database credentials or direct database access.
- Do not replace real-time critical workflows with polling.
- Do manage operational business policies and approval workflows exclusively in the Shell.
- Do generate deterministic Alembic migrations for Shell data-model changes.
- Do maintain API specifications and `.ai/adapter_schema.md` for every adapter.

## Status

VibeCore ERP is establishing the reusable foundation and contracts for future modules. The architecture is the product boundary: every implementation should make it easier to reuse the core, replace an integration, and shape the UI around a real business.

## License

Released under the [MIT License](LICENSE).
