# SIFEN Adapter

The SIFEN adapter is an isolated service providing integration with the Paraguayan National Electronic Invoicing System (SIFEN / DNIT / SET) according to [ADR 0007](../../.ai/adr/0007-sifen-adapter-boundary-and-rollout.md).

## Capabilities

1. **Automatic RUC Profile Resolver (`SifenProfileResolver`):**
   - Inspects the registered tax obligations (`Obligaciones`) of the issuing Mandant:
     - **Code 700 (IRE General):** Emits Factura Electrónica (`iTiDE = 1`), liquidates IVA 10%, 5%, and Exento.
     - **Code 701 (IRE Simple):** Emits Factura Electrónica (`iTiDE = 1`), liquidates IVA 10%, 5%, and Exento.
     - **Code 702 (IRE Resimple):** Emits Boleta Resimple Electrónica (`iTiDE = 4`), exempt from IVA (gross amount only).

2. **SIFEN DTE XML Generator (`SifenXmlGenerator`):**
   - Implements SIFEN Technical Manual Version 150.
   - Computes 44-digit CDC using official Modulo 11 check digit algorithm.
   - Generates schema-compliant XML structures:
     - Factura Electrónica (`iTiDE = 1`): Includes `gCamFE`, `gCamIVA` with `iAfecIVA`, `dPropIVA`, `dTasaIVA`, `dBasGravIVA`, `dLiqIVAItem`, and `gTotSub` VAT breakdown.
     - Boleta Resimple Electrónica (`iTiDE = 4`): Marked exempt (`iAfecIVA = 3`), zero VAT calculation, only gross amounts in `gTotSub`.

3. **Offline-Contingencia & Durable Outbox Queue (`SifenContingenciaEngine`):**
   - **Local SQLite Persistence with WAL:** Write-Ahead Logging (`PRAGMA journal_mode = WAL`) guarantees zero document loss on unexpected power cuts or SIGKILL.
   - **Status Tracking:** Tracks full document lifecycle: `DRAFT`, `QUEUED_OFFLINE`, `TRANSMITTING`, `ACCEPTED`, `REJECTED`, `EXPIRED (>72h)`.
   - **Automatic Failover (Circuit Breaker):** Automatically trips on network outage or SIFEN gateway timeouts, immediately falling back to Contingency (`iTipEmi = 2`).
   - **Instant KuDE Customer Receipt & QR:** Generates official SIFEN KuDE thermal POS receipts and QR codes via `pysifen` and `segno` instantly, ensuring zero checkout delays at local tills.
   - **Background Batch Sync:** Transmits queued offline batches upon network restoration with exponential backoff.
   - **72h Legal Deadline Enforcement:** Monitors DNIT 72-hour submission deadline, raising warnings (<24h, <12h) and transitioning past-deadline documents to `EXPIRED`.

## Architecture & Boundary

Per ADR 0007, this adapter operates outside the Finance Core. It does not connect directly to the PostgreSQL database. Communication happens via typed payloads and authenticated REST endpoints defined in `openapi.json`.

