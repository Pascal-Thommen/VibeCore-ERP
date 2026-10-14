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

## Architecture & Boundary

Per ADR 0007, this adapter operates outside the Finance Core. It does not connect directly to the PostgreSQL database. Communication happens via typed payloads and authenticated REST endpoints defined in `openapi.json`.
