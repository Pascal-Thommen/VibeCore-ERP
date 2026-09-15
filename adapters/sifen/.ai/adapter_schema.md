# SIFEN Adapter Contract

**Status:** Placeholder — the mock adapter contract is defined before the first
implementation in the adapter phase.

The SIFEN adapter follows [ADR 0007](../../../.ai/adr/0007-sifen-adapter-boundary-and-rollout.md).
It will expose `openapi.json`, accept signed idempotent Core events, and never
connect directly to PostgreSQL.
