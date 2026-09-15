# Adapters

Every adapter is an isolated service. It communicates with the Core only through
authenticated REST APIs and signed events; direct PostgreSQL access is forbidden.

Each adapter must include:

```text
<adapter>/
├── .ai/adapter_schema.md
├── blueprints/             # Required only when reusable UI components exist
├── openapi.json
└── README.md
```

Use the repository template at `../.ai/adapter_schema.md` to create the adapter
contract before implementing the integration.
