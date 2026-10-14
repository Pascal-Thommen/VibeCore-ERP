# SIFEN Adapter Microservice

The SIFEN adapter is an isolated microservice container providing integration with the Paraguayan National Electronic Invoicing System (SIFEN / DNIT / SET) according to [ADR 0007](../../.ai/adr/0007-sifen-adapter-boundary-and-rollout.md) and [ADR 0008](../../.ai/adr/0008-library-and-implementation-policy.md).

## Capabilities

1. **FastAPI Application Server (`sifen.server:app`):**
   - Implements REST endpoints documented in `openapi.json`:
     - `POST /api/v1/sifen/resolve`: Resolves Mandant RUC profile to DTE type and tax behavior.
     - `POST /api/v1/sifen/generate-xml`: Produces SIFEN v150 XML.
     - `POST /api/v1/sifen/sign`: Signs XML with XMLDSig and adds official KuDE QR code URL.
     - `POST /api/v1/sifen/sign-and-send`: Complete pipeline from invoice data to digital signature, QR generation, and SOAP 1.2 / mTLS transmission to DNIT.
     - `GET /health` & `GET /api/v1/sifen/health`: Health monitoring.

2. **pysifen Integration:**
   - **Digital XMLDSig Signing:** Uses `pysifen.signing.backends.pkcs12.FirmantePkcs12` and `firmar_documento` with PKCS#12 certificates.
   - **QR Code URL Generation:** Uses `pysifen.qr.DatosQr` and `pysifen.qr.generar_url_qr` adhering to SIFEN v150 § 13.8.
   - **Fields Outside Signature (`gCamFuFD`):** Injected via `pysifen.documento.sobre.agregar_campos_fuera_de_firma`.

3. **SOAP 1.2 / mTLS Client (`SifenSoapClient`):**
   - Constructs official SOAP 1.2 envelopes (`rEnviDe`, `dId`, `xDE`).
   - Supports mutual TLS (mTLS) client certificate authentication.
   - Seamless test simulation mode for CI/CD and offline verification.

4. **Containerization & Independence:**
   - Runs in isolated Docker container on port 8001.
   - Completely independent from Odoo, PostgreSQL, or backend databases.

## Running Locally

```bash
uvicorn sifen.server:app --host 0.0.0.0 --port 8001
```

## Running with Docker

```bash
docker compose up sifen-adapter
```
