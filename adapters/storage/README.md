# VibeCore S3-Compatible Object Storage Adapter

Autonomer, wiederverwendbarer Microservice für S3-kompatiblen Objektspeicher (AWS S3, Cloudflare R2, MinIO, Wasabi) im VibeCore ERP Ökosystem (`adapters/storage`).

## Überblick und Kernfunktionen

* **Streaming Direct Upload:** Überträgt Dokumente und Belege direkt in den S3-Speicher mit blockweiser SHA-256 Integritätsprüfung ohne hohe RAM-Belastung.
* **Pre-Signed Upload URLs:** Erzeugt kryptografisch signierte PUT-URLs mit TTL. Ermöglicht Web-Clients und Mobil-Apps den direkten Datei-Upload in den Objektspeicher, wodurch Serverbandbreite und CPU geschont werden.
* **Pre-Signed Download URLs:** Generiert zeitlich begrenzte GET-Links mit dynamischer `response-content-disposition` für saubere Dateinamen beim Client-Download.
* **Metadaten und Integrität:** Liest Dateigröße, Content-Type, ETag und persistierte SHA-256 Prüfsummen aus den S3-Objekt-Headern aus.
* **Sichere Löschung:** Prüft vor der Entfernung die Objektexistenz und löscht Objekte zuverlässig.
* **Observability (Säule 4):** Lückenlose Traceability durch `X-Correlation-ID`, strukturierte JSON-Logs und Container-Healthchecks (`/health`, `/ready`).
* **Sicherheit (Säule 3):** Optionaler Schutz aller Schnittstellen über den Header `X-API-Key`, Whitelist für MIME-Types und Schutz vor Directory-Traversal Pfadangriffen.

---

## Verzeichnisstruktur

```text
adapters/storage/
├── .ai/
│   └── adapter_schema.md        # Standardisierter Adapter-Vertrag
├── app/
│   ├── audit.py                 # Säule 4: Observability und JSON-Logging
│   ├── client.py                # S3-Client mit Boto3, Timeouts und Retries
│   ├── config.py                # Pydantic Settings Umgebungskonfiguration
│   ├── main.py                  # FastAPI Entrypoint und Middlewares
│   ├── models.py                # Pydantic Schemas und Datenmodelle
│   ├── routers/
│   │   ├── health.py            # /health und /ready Probes
│   │   └── storage.py           # REST-Endpunkte für Speicheroperationen
│   └── service.py               # Service-Layer mit Validierung
├── tests/                       # Umfassende automatisierte Testsuite
├── .dockerignore
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── openapi.json                 # Maschinenlesbarer OpenAPI 3.1 Kontrakt
├── pyproject.toml
├── requirements.txt
├── RESEARCH_DOSSIER.md          # Recherche und Anbieter-Vergleich
└── README.md
```

---

## Konfiguration (Umgebungsvariablen)

| Variable | Beschreibung | Standardwert |
| :--- | :--- | :--- |
| `STORAGE_ENDPOINT_URL` | S3 Endpoint (MinIO, Cloudflare R2, Wasabi; leer für AWS S3) | `None` |
| `STORAGE_PUBLIC_ENDPOINT_URL` | Öffentliche Basis-URL für signierte URLs bei Docker-Netzwerken | `None` |
| `STORAGE_ACCESS_KEY` | S3 Access Key ID | `minioadmin` |
| `STORAGE_SECRET_KEY` | S3 Secret Access Key | `minioadmin` |
| `STORAGE_BUCKET` | Ziel-Bucket für Dokumente und Belege | `vibecore-documents` |
| `STORAGE_REGION` | S3-Region | `us-east-1` |
| `STORAGE_ADDRESSING_STYLE` | Adressierung: `auto`, `path` oder `virtual` (`path` für MinIO) | `auto` |
| `STORAGE_API_KEY` | Optionaler API-Key zur Absicherung via `X-API-Key` Header | `None` |
| `STORAGE_DEFAULT_PRESIGNED_TTL`| Standard-Gültigkeitsdauer für signierte URLs in Sekunden | `3600` |
| `STORAGE_MAX_UPLOAD_SIZE_BYTES`| Maximal zulässige Upload-Größe in Bytes (z. B. 50 MB) | `52428800` |
| `STORAGE_CONNECT_TIMEOUT` | Socket Verbindungs-Timeout in Sekunden | `5.0` |
| `STORAGE_READ_TIMEOUT` | Socket Lese-Timeout in Sekunden | `30.0` |
| `STORAGE_MAX_RETRIES` | Maximale automatische Wiederholungen bei Netzwerkfehlern | `3` |

---

## API-Endpunkte

### 1. Healthchecks
* `GET /health`: Liveness-Probe für Container-Orchestrierung.
* `GET /ready`: Readiness-Probe, prüft Erreichbarkeit des konfigurierten S3-Buckets.

### 2. Speicher-Operationen
* `POST /api/v1/storage/upload`: Multipart-Upload für Dateien (`file`, optional `file_id`, `custom_metadata`).
* `POST /api/v1/storage/presigned-upload`: Erzeugung kryptografisch signierter Upload-URLs.
* `POST /api/v1/storage/presigned-download`: Erzeugung temporärer Download-URLs mit Originalnamen.
* `GET /api/v1/storage/files/{file_id}/metadata`: Abfrage von Metadaten und SHA-256 Prüfsumme.
* `DELETE /api/v1/storage/files/{file_id}`: Sicheres Löschen einer gespeicherten Datei.

---

## Lokale Ausführung und Tests

### Start via Docker Compose
```bash
docker compose up -d
```

### Manuelle Ausführung
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```

### Automatisierte Tests ausführen
```bash
pytest tests/ -v --cov=app
```
