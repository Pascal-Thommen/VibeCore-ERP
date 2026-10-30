# Adapter Schema: SIFEN Fiscal Adapter (Paraguay DTE)

## Adapter identity

* **Name:** `sifen-fiscal-adapter`
* **Version:** `1.0.0`
* **Owner:** VibeCore ERP Core Team (Fiscal & Compliance Paraguay)
* **OpenAPI:** `openapi.json`

## Core contract

* **Inbound endpoints (Core to Adapter):**
  * `POST /api/v1/sifen/resolve`: Resolves Mandant RUC obligations (700 IRE General, 701 IRE Simple, 702 IRE Resimple) into DTE type (`iTiDE = 1` Factura Electrónica vs `iTiDE = 4` Boleta Resimple) and IVA policy.
  * `POST /api/v1/sifen/generate-xml`: Generates official SIFEN v150 XML (`rDE`) with 44-digit Modulo-11 CDC and gross-inclusive IVA liquidation per Ley 6380/19.
  * `POST /api/v1/sifen/submit`: Generates DTE XML, persists it in the local SQLite Outbox Queue, and attempts live SOAP 1.2 transmission (`rEnviDe`) to SIFEN. On network timeout or upstream 5xx outage, the DTE remains safely queued (`QUEUED`).
  * `POST /api/v1/sifen/outbox/flush`: Retries all `QUEUED` DTEs in FIFO order when connectivity is restored.
  * `GET /api/v1/sifen/outbox`: Lists DTE records in the persistent Outbox Queue (optional `?status=QUEUED|ACCEPTED|REJECTED`).
  * `GET /api/v1/sifen/outbox/{cdc}`: Retrieves DTE submission and Outbox status by 44-digit CDC.
  * `GET /health`: Liveness probe.
  * `GET /ready`: Readiness probe verifying local Outbox DB connectivity and SIFEN endpoint configuration.

* **Outbound endpoints (Adapter to SIFEN / DNIT):**
  * `POST {SIFEN_BASE_URL}/de/ws/sync/recibe.wsdl`: Synchronous SOAP 1.2 DTE transmission (`rEnviDe` / `rRetEnviDe`).

* **Authentication:**
  * Internal endpoints secured via `X-Adapter-Key` or `Authorization: Bearer <token>` when `ADAPTER_API_KEY` is configured.

* **Idempotency key:**
  * Header `X-Idempotency-Key` and deterministic 44-digit SIFEN `cdc` prevent duplicate DTE submissions.

* **Retry and recovery:**
  * Explicit HTTP timeout (`REQUEST_TIMEOUT_SECONDS`) and exponential backoff retries (`MAX_RETRIES`).
  * Persistent SQLite Outbox Queue (`sifen_outbox`) guarantees zero DTE loss during DNIT/SET network outages.

## Payload evolution

All cross-boundary JSON payloads support optional `meta` and `custom_data` dictionaries.

## Security boundary

This adapter operates in isolation outside the Finance Core per ADR 0007 and never accesses the Core PostgreSQL database directly.
