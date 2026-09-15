VibeCore ERP

A composable, AI-first ERP foundation for SMEs — built around the way a business actually works.

VibeCore ERP is the architectural standard behind fast, durable, client-specific ERP systems. It separates the financial truth of a business from the interfaces, automations, and integrations built around it.

Instead of repeatedly rebuilding generic CRUD applications, teams define dependable data models and workflows once. AI agents then assemble the client-specific shell and integrations around a protected accounting core.

Core principle: the business process shapes the software — never the other way around.

Why VibeCore?

Traditional ERPs force every company into the same screens, modules, and processes. VibeCore takes the opposite approach:

Finance stays reliable. Double-entry accounting, tax logic, and financial integrity live in one protected core.

The client experience stays flexible. Each business gets a shell that matches its real operations: a scale at a gold buyer, a counter at a store, a mobile workflow in the field.

Integrations stay replaceable. WhatsApp, e-invoicing, banking, OCR, and future services run outside the core as isolated adapters.

AI accelerates delivery without gaining financial authority. AI can create workflows and draft transactions; a human approves financial execution.

VibeCore is designed for micro, small, and medium-sized enterprises (MSMEs), especially teams that need bespoke operational software without bespoke financial foundations every time.

Architecture at a glance

flowchart LR
  U[Client-specific UI / Custom Shell] -->|REST / JSON & MCP| C
  C[Immutable Finance Core\nFastAPI + PostgreSQL]
  C -->|real-time events / webhooks| A1[SIFEN adapter\nCore-bound / Compliance]
  S[Shell workspace\nclient business logic] -->|events / webhooks| A2[WhatsApp adapter\nShell-bound / Workflow]
  A1 -->|REST / JSON| C
  A2 -->|REST / JSON| C

  subgraph PostgreSQL
    C1[core schema\nprotected financial truth]
    S1[shell schema\nclient workspace]
  end
  C --- C1
  S --- S1


Layer

Responsibility

Freedom to change

Finance Core (/backend/core)

Accounting, items, taxes, transaction integrity

Protected (Immutable)

Shell workspace (shell schema)

Client-specific processes, data, and business logic

Extensible / Fully customizable

Adapters (/adapters)

External services and provider-specific logic

Isolated and replaceable

Client UI / Shell (/frontend or custom)

Task-focused client interface (Reference implementation or custom stack)

Completely open / Choice of stack

The two-tier standard

VibeCore ERP — the global standard

The global architecture is deliberately portable:

Headless by design. The Finance Core owns no user interface and interacts solely via REST/JSON APIs and MCP endpoints.

Process proximity. Client workflows determine the Shell experience; standard ERP screens do not.

Prompt as code. Define the model and contracts clearly; let AI generate the repetitive integration work.

Modern, minimal foundation. The Core uses raw Python with FastAPI and PostgreSQL — no legacy ERP framework.

VibeCore PY — the Paraguayan implementation

VibeCore-PY applies the global standard to Paraguay. Implementations in this context must:

Use the Paraguayan Chart of Accounts under Ley 6380/19.

Validate RUC values, including the check digit (DV).

Prioritize a SIFEN / e-Kuatia adapter for electronic invoices.

Support Marangatú export formats, including RG 90 requirements.

Model the three IVA treatments for every applicable financial transaction: exempt, 5%, and 10%.

Compliance is a product requirement, not an adapter detail. Local tax and e-invoicing rules must be independently reviewed and kept current before production use.

Layer A — Immutable Finance Core

The Finance Core is one monolithic service and database boundary, chosen intentionally for ACID-safe financial transactions.

Required stack: Python, FastAPI, PostgreSQL.

The core PostgreSQL schema is limited to the durable financial domain:

Double-entry accounting

Items and financial master data

Tax calculation and classification

Financial transaction state

Core invariants

AI agents must not modify the core schema.

Financial records must preserve balanced, auditable double-entry semantics.

Every financial action records an actor, such as HUMAN_CARLOS, SYSTEM_CRON, or AI_AGENT.

A transaction drafted or initiated by AI remains DRAFT until a human approves it through the Shell.

Core changes require explicit architecture-owner approval and a reviewed migration path.

The Core is intentionally small. It should know financial truth, not the peculiarities of an individual client’s operational workflow.

The Shell workspace

The shell PostgreSQL schema is where a client’s actual business lives.

It may contain client-specific tables, views, and workflows — for example scale readings for a precious-metals buyer, delivery routes, service orders, or shop-floor data. Shell tables may reference Core primary keys through foreign keys, but must not redefine or bypass financial rules.

Deterministic schema changes (using tools like Alembic) ensure that client workspaces remain reproducible and safe to apply.

Layer B — Adapters (Core-Bound vs. Shell-Bound)

Adapters connect VibeCore to the outside world. They run as independent Dockerized microservices and are free to use the language and runtime that best suits the provider: Node.js, Go, Python, or another appropriate stack.

Depending on their function, adapters attach to different architectural boundaries:

Core-Bound Adapters (Compliance & Financial Truth):

Services like SIFEN (e-Kuatia) attach directly to the Finance Core because electronic invoicing and tax validations are tied directly to financial transaction state changes.

They trigger via real-time Core events or webhooks to ensure compliance without human delay.

Shell-Bound Adapters (Operational Workflows & Messaging):

Services like WhatsApp notifications, customer portals, or field-service tracking attach to the Shell or operate as independent operational microservices.

They drive customer interaction and business workflows without touching the protected accounting core.

Adapter contract

Communicate with the Core and Shell exclusively through versioned JSON over REST APIs.

Never connect directly to PostgreSQL. Database isolation is absolute.

Expose an openapi.json specification.

Include an AI-readable contract at .ai/adapter_schema.md.

Include a /blueprints directory when the adapter needs reusable user-interface components or reference layouts.

Treat provider credentials, signing keys, and secrets as runtime configuration — never commit them.

Real-time first, recovery second

Critical business actions must use real-time events or webhooks. For example, a POS checkout that needs a SIFEN e-invoice triggers the SIFEN adapter immediately.

An adapter may poll APIs only for recovery, such as reconciling missed work after startup. Polling is not a substitute for a real-time business workflow.

Layer C — Client Interfaces & Vibe Shell

The client interface layer is completely open. While the reference implementation provides a Vibe Shell built with modern frameworks and Tailwind CSS, teams are fully free to choose any frontend stack, mobile wrapper, or rapid prototyping tool (such as Streamlit) that suits their operational needs.

The interface owns workflow design, visual identity, and task-specific interaction. It should make the client’s daily work feel native, while the Finance Core remains invisible and dependable underneath.

For complex integrations, adapter repositories may ship generic frontend blueprints in /blueprints. AI agents can copy or adapt these components to fit whatever frontend stack is chosen.

API and MCP (Model Context Protocol) Specifications

VibeCore ERP natively bridges programmatic access through standard REST endpoints and AI context protocols.

1. REST / JSON API Standards

Versioning: All routes are versioned under /api/v1/....

Format: Strict JSON request and response bodies.

Authentication: Bearer token authentication mapped to specific actor identities (HUMAN_*, SYSTEM_*, AI_AGENT).

Idempotency: Mutating requests require idempotency keys to prevent duplicate journal entries during network failures.

2. Model Context Protocol (MCP) Integration

To enable AI development assistants (like Claude Desktop, Cursor, or custom agents) to safely inspect models, draft entries, and query documentation without direct database access, the Finance Core and adapters expose standard MCP servers:

Tools: Exposes approved operations such as draft_journal_entry, validate_ruc, or calculate_iva_split.

Resources: Provides read-only context schemas (core://schema/accounts, adapter://sifen/spec).

Prompts: Standardized prompt templates for guiding AI agents through compliant transaction drafting under Paraguayan tax laws.

Data and API conventions

Design for the next unknown requirement

Every JSON payload exchanged among the Core, Shell, and Adapters must provide an optional extension object:

{
  "id": "txn_01J...",
  "status": "DRAFT",
  "meta": {},
  "custom_data": {}
}


Use meta for interoperable technical or integration metadata. Use custom_data for domain-specific extensions. Consumers must tolerate fields they do not recognize. This keeps contracts forward-compatible without breaking older clients.

State and traceability

Record the actor responsible for every financial action.

Preserve approval history and audit context.

Model AI-originated financial work as DRAFT until human approval.

Prefer explicit, idempotent API operations for event retries and recovery.

Repository conventions (Reference Layout)

Depending on your project structure, modules can be organized flexibly. A common reference layout is:

.
├── backend/                # FastAPI Finance Core and Shell services
│   ├── core/                # Protected financial domain
│   └── shell/               # Client-specific workspace domain
├── frontend/                # Optional reference Vibe Shell (or custom stack)
├── adapters/                # Isolated integration services (Core-bound & Shell-bound)
│   └── <adapter>/
│       ├── .ai/adapter_schema.md
│       ├── blueprints/      # Optional reusable UI components/blueprints
│       └── openapi.json
├── migrations/              # Deterministic database migrations
└── docs/                    # Architecture decisions and operating guides


Instructions for AI agents and contributors

Before implementing a feature, identify its layer.

If you need to…

Build it in…

Post a journal entry, calculate tax, or enforce accounting rules

Finance Core

Capture a client-specific operational process

Shell schema + Chosen UI Shell

Connect a compliance/tax service (e.g., SIFEN)

Core-Bound Adapter

Connect an operational/messaging service (e.g., WhatsApp)

Shell-Bound Adapter

Change a financial record proposed by AI

Shell approval flow, then Core after human approval

Non-negotiable rules:

Do not change the core schema without explicit architecture-owner approval.

Do not give adapters database credentials or direct database access.

Do not replace real-time critical workflows with polling.

Do not finalize AI-created financial work without a human approval action.

Maintain deterministic migrations for data-model changes.

Do maintain API specifications and .ai/adapter_schema.md for every adapter.

Status

VibeCore ERP establishes a flexible, composable foundation for bespoke enterprise applications. The architecture protects financial truth while allowing absolute freedom in how operational workflows and user interfaces are built.

License

Released under the MIT License.
