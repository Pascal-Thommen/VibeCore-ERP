# SIFEN Adapter

The SIFEN adapter is an isolated microservice providing integration with the Paraguayan National Electronic Invoicing System (SIFEN / DNIT / SET) according to [ADR 0007](../../.ai/adr/0007-sifen-adapter-boundary-and-rollout.md).

## Capabilities

1. **Automatic RUC Profile Resolver (`SifenProfileResolver`):**
   - Inspects the registered tax obligations (`Obligaciones`) of the issuing Mandant:
     - **Code 700 (IRE General):** Emits Factura Electrónica (`iTiDE = 1`), liquidates gross-inclusive IVA 10% (`Brutto / 11`), 5% (`Brutto / 21`), and Exento (`0%`) per Ley 6380/19.
     - **Code 701 (IRE Simple):** Emits Factura Electrónica (`iTiDE = 1`), liquidates gross-inclusive IVA 10%, 5%, and Exento.
     - **Code 702 (IRE Resimple):** Emits Boleta Resimple Electrónica (`iTiDE = 4`), exempt from IVA (gross amount only).

2. **SIFEN DTE XML Generator (`SifenXmlGenerator`):**
   - Implements SIFEN Technical Manual Version 150.
   - Computes 44-digit CDC using official Modulo 11 check digit algorithm.
   - Guarantees exact PYG Guaraní and decimal balance (`dBasGravIVA + dLiqIVAItem == dTotOpeItem`).

3. **Persistent Outbox Queue & SOAP 1.2 Client (`SifenService`, `SifenClient`):**
   - Wraps generated `<rDE>` documents in official SOAP 1.2 `<rEnviDe>` envelopes and transmits them to SIFEN (`/de/ws/sync/recibe.wsdl`) with explicit timeouts and retries.
   - Persists every DTE in a local SQLite Outbox (`sifen_outbox`) prior to transmission. If SIFEN is unreachable or times out, the DTE remains `QUEUED` and can be flushed via `POST /api/v1/sifen/outbox/flush` without data loss.

## Architecture & Boundary

Per ADR 0007, this adapter operates outside the Finance Core and never connects directly to the Core PostgreSQL database.
