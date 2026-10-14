# SIFEN Adapter Contract

**Status:** IMPLEMENTED (Dynamic DTE & RUC Profile Resolver Phase)

The SIFEN adapter follows [ADR 0007](../../../.ai/adr/0007-sifen-adapter-boundary-and-rollout.md).
It exposes `openapi.json`, accepts signed idempotent Core events, and never connects directly to PostgreSQL.

## Supported Electronic Document Types (iTiDE)

| iTiDE | Document Type | Tax Regime | IVA Handling |
|-------|---------------|------------|--------------|
| 1 (`01`) | Factura Electrónica | IRE General (700), IRE Simple (701) | Full IVA calculation (10%, 5%, Exento) with `gCamIVA`, `dBasGravIVA`, `dLiqIVAItem` |
| 4 (`04`) | Boleta Resimple Electrónica | IRE Resimple (702) | Tax-exempt marked (`iAfecIVA = 3`), no IVA calculation, gross amount only |

## Offline-Contingencia & Durable Outbox Lifecycle

When SIFEN network outages or gateway timeouts occur, the adapter seamlessly switches to Contingencia (`iTipEmi = 2`).

### Emission Modes (`iTipEmi`)

- **1 (`Normal`):** Direct online synchronous submission to DNIT SIFEN.
- **2 (`Contingencia`):** Offline emission with local CDC generation, instantaneous KuDE receipt / QR delivery, and local SQLite WAL enqueueing.

### Outbox Status Lifecycle

```
[ DRAFT ] ---> [ QUEUED_OFFLINE ] <---> [ TRANSMITTING ] ---> [ ACCEPTED ]
                      |                       |
                      | (fatal rejection)     | (fatal rejection)
                      v                       v
                 [ REJECTED ]            [ REJECTED ]
                      |
                      | (elapsed > 72h)
                      v
                 [ EXPIRED ]
```

- `DRAFT`: Prepared document staging.
- `QUEUED_OFFLINE`: Stored in SQLite WAL, awaiting background transmission.
- `TRANSMITTING`: Worker attempting batch delivery to DNIT SIFEN.
- `ACCEPTED`: Acknowledged and signed by DNIT with official SIFEN protocol.
- `REJECTED`: Permanently rejected due to tax authority rule violation.
- `EXPIRED`: Failed to transmit within legal 72-hour window.

