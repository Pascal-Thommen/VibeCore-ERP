# Adapter Schema: S3 Object Storage Adapter

## Adapter identity

- **Name:** vibecore-storage-adapter
- **Version:** 0.1.0
- **Owner:** VibeCore Infrastructure Team
- **OpenAPI:** openapi.json

## Core contract

- **Inbound endpoints/events:**
  - `POST /api/v1/storage/upload`: Direkter Streaming-Upload von Dokumenten und Belegen
  - `POST /api/v1/storage/presigned-upload`: Erzeugung kryptografisch signierter Upload-URLs mit TTL
  - `POST /api/v1/storage/presigned-download`: Erzeugung zeitlich beschränkter Download-URLs
  - `GET /api/v1/storage/files/{file_id}/metadata`: Abfrage von Dateigröße, MIME-Typ, SHA-256 Hash und Metadaten
  - `DELETE /api/v1/storage/files/{file_id}`: Sichere Löschung gespeicherter Objekte
  - `GET /health`: Container Liveness-Check
  - `GET /ready`: Container Readiness-Check mit S3 Bucket Connectivity Test
- **Outbound endpoints/events:**
  - S3 REST API (AWS S3, Cloudflare R2, MinIO, Wasabi) via SigV4
- **Authentication:**
  - API Key Authentifizierung via Header `X-API-Key`
- **Idempotency key:**
  - `Idempotency-Key` Header bei Upload-Operationen oder deterministische `file_id`
- **Correlation ID:**
  - `X-Correlation-ID` Header bei allen Inbound- und Outbound-Operationen
- **Retry and recovery:**
  - Standardisierter Exponential-Backoff (3 Versuche) bei Netzwerkunterbrechungen und S3 500/503 Fehlern
  - Saubere Timeouts (5s Connect, 30s Read)

## Payload evolution

Alle JSON-Payloads unterstützen optionale `custom_metadata` Objekte. Fehlerantworten liefern einheitlich das Schema `ErrorResponse` mit `error`, `message`, `detail`, `trace_id` und `timestamp`. Änderungen am Datenvertrag erfolgen abwärtskompatibel.

## Security boundary

Dieser Adapter besitzt keinen direkten Datenbankzugriff auf PostgreSQL. Erforderliche Secrets (`STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`, `STORAGE_API_KEY`) werden ausschließlich über Umgebungsvariablen oder Docker Secrets injiziert. Schlüsselrotation erfolgt ohne Downtime durch Aktualisierung der Umgebungskonfiguration.
