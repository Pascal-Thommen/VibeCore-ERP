# SIFEN Adapter Contract

**Status:** IMPLEMENTED (Dynamic DTE & RUC Profile Resolver Phase)

The SIFEN adapter follows [ADR 0007](../../../.ai/adr/0007-sifen-adapter-boundary-and-rollout.md).
It exposes `openapi.json`, accepts signed idempotent Core events, and never connects directly to PostgreSQL.

## Supported Electronic Document Types (iTiDE)

| iTiDE | Document Type | Tax Regime | IVA Handling |
|-------|---------------|------------|--------------|
| 1 (`01`) | Factura Electrónica | IRE General (700), IRE Simple (701) | Full IVA calculation (10%, 5%, Exento) with `gCamIVA`, `dBasGravIVA`, `dLiqIVAItem` |
| 4 (`04`) | Boleta Resimple Electrónica | IRE Resimple (702) | Tax-exempt marked (`iAfecIVA = 3`), no IVA calculation, gross amount only |
