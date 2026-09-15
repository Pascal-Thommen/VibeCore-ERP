# AI Architecture Workspace

This directory is the machine-readable architecture workspace for VibeCore ERP.
It is versioned alongside the code so that AI agents and human contributors work
from the same decisions.

| Path | Purpose |
| --- | --- |
| `ARCHITECTURE.md` | Binding system constraints and decision hierarchy |
| `adr/` | Accepted Architecture Decision Records (ADRs) |
| `adapter_schema.md` | Required adapter-contract template |

Read `ARCHITECTURE.md` first, then every ADR relevant to the requested change.

### Decision hierarchy

1. Approved ADRs
2. `ARCHITECTURE.md`
3. Repository README and implementation documentation
4. Local module documentation

An ADR is immutable after acceptance. Replace or supersede it with a new ADR;
do not silently rewrite architectural history.
