# SIFEN Adapter Contract

**Status:** IMPLEMENTED (Microservice Container & pysifen Integration Phase)

The SIFEN adapter follows [ADR 0007](../../../.ai/adr/0007-sifen-adapter-boundary-and-rollout.md) and [ADR 0008](../../../.ai/adr/0008-library-and-implementation-policy.md).
It exposes `openapi.json`, runs as an isolated FastAPI container without Odoo or database dependencies, and communicates via typed REST endpoints.

## Endpoints

- `GET /health` and `GET /api/v1/sifen/health`: Health status.
- `POST /api/v1/sifen/resolve`: Resolves Mandant RUC profile into DTE type and tax calculation policy.
- `POST /api/v1/sifen/generate-xml`: Generates schema-compliant SIFEN v150 XML.
- `POST /api/v1/sifen/sign`: Cryptographically signs SIFEN XML using PKCS#12 via `pysifen` and appends KuDE QR URL (`gCamFuFD`).
- `POST /api/v1/sifen/sign-and-send`: Full lifecycle: XML generation, XMLDSig digital signature, KuDE QR URL generation, and SOAP 1.2 / mTLS transmission to DNIT e-Kuatia (with simulation support).

## Supported Electronic Document Types (iTiDE)

| iTiDE | Document Type | Tax Regime | IVA Handling |
|-------|---------------|------------|--------------|
| 1 (`01`) | Factura Electrónica | IRE General (700), IRE Simple (701) | Full IVA calculation (10%, 5%, Exento) with `gCamIVA`, `dBasGravIVA`, `dLiqIVAItem` |
| 4 (`04`) | Boleta Resimple Electrónica | IRE Resimple (702) | Tax-exempt marked (`iAfecIVA = 3`), no IVA calculation, gross amount only |

## Security & Certificates

- Uses PKCS#12 software certificates (`.p12`) loaded into `pysifen.signing.backends.pkcs12.FirmantePkcs12`.
- Generates official W3C XMLDSig signatures (`enveloped-signature`, `c14n` exclusive, RSA-SHA256).
- QR code complies with DNIT SIFEN Technical Manual v150 § 13.8 (SHA-256 hash incorporating taxpayer CSC secret).
- mTLS client authentication supported for DNIT SOAP 1.2 endpoints.
