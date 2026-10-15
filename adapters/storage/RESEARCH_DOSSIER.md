# S3-Kompatibler Object Storage Microservice Adapter: Recherche und Spezifikation

Dieses Dossier dokumentiert die Recherche, Bibliotheken-Evaluation und Schnittstellen-Spezifikation für den Objektspeicher-Microservice (`adapters/storage`) im VibeCore ERP Ökosystem.

## 1. Evaluierung von Bibliotheken und Best Practices

### 1.1 Evaluierte Python S3 Bibliotheken

1. **`boto3` und `botocore` (Offizielle AWS SDK)**
   * **Architektur:** Synchrones Standard-SDK der AWS Foundation, nutzt `urllib3` und `botocore`.
   * **Vorteile:**
     * Höchste Reife, Stabilität und Dokumentation weltweit.
     * Vollständige, fehlerfreie Unterstützung der AWS Signature Version 4 (SigV4).
     * Umfassende Konfigurationsmöglichkeiten für Retries (Standard / Adaptive Mode) und Timeouts (`connect_timeout`, `read_timeout`).
     * Funktioniert nahtlos mit AWS S3, Cloudflare R2, MinIO und Wasabi.
     * Entspricht ADR 0008 (Mature-Library Implementation Policy).
   * **Einsatz in FastAPI:**
     * Durch Auslagerung von blockierenden Netzwerkoperationen in Worker-Threads via `asyncio.to_thread` bleibt die FastAPI Event-Loop vollständig reaktiv und blockierungsfrei.

2. **`aioboto3` (Asynchroner Wrapper um botocore / aiobotocore)**
   * **Architektur:** Asynchroner Fork von botocore unter Nutzung von `aiohttp`.
   * **Bewertung:**
     * Bietet native `async/await` Syntax für S3 Calls.
     * Nachteil: Häufige Inkompatibilitäten bei Minor-Updates von boto3/botocore durch Monkey-Patching.
     * Erfordert komplexe Session-Verwaltung mit verschachtelten Context-Managern.
     * Zusätzliche Fehlerquellen bei Connection Pools und Streaming-Objekten unter Python 3.12 und 3.14.

3. **`minio-py` (Offizielles MinIO Python SDK)**
   * **Architektur:** Eigenständiges SDK von MinIO Inc.
   * **Bewertung:**
     * Schlank und einfach für reine MinIO Deployments.
     * Nachteil: Proprietäre API-Struktur, weicht in Details von der AWS Signature Spezifikation ab.
     * Eingeschränkte Flexibilität bei Cloudflare R2 und Wasabi Custom Domains.

### 1.2 Architekturentscheidung
Gemäß ADR 0008 setzen wir auf das bewährte Tandem aus **`boto3`**, **`botocore`** und **`FastAPI`**. Blockierende S3-I/O-Operationen werden mit `asyncio.to_thread` thread-isoliert ausgeführt. Dies garantiert maximale Protokollstabilität, volle Kompatibilität mit allen S3-Providern und minimale Wartungskomplexität.

---

## 2. Pre-Signed URL Architektur

### 2.1 Funktionsweise und kryptografische Signatur
Pre-Signed URLs ermöglichen autorisierte Datei-Uploads und Downloads direkt zwischen Client (Web-Frontend, Mobile App, Core-Worker) und dem Objektspeicher.

* **Signatur-Verfahren:** AWS SigV4 (`AWS4-HMAC-SHA256`).
* **Sicherheit:** Die URL enthält Access-Key, Zeitstempel, Gültigkeitsdauer (TTL) und die HMAC-Signatur über den HTTP-Verb, den Bucket, den Key und optionale Header.
* **Payload-Vermeidung:** Weder die Dateidaten noch sensible Provider-Credentials laufen über den VibeCore App-Server. Der Microservice generiert lediglich den kryptografischen Link.
* **Bandbreite und RAM:** Entlastung des Microservice-Arbeitsspeichers um 100 Prozent bei Großdateien (z. B. PDF-Scans, Rechnungsarchive).

### 2.2 Upload-Workflow (Pre-Signed PUT)
1. Client sendet Anfrage `POST /api/v1/storage/presigned-upload` mit Dateiname, MIME-Type und optionaler Prüfsumme.
2. Microservice validiert die Anfrage (Erlaubte Dateitypen, TTL zwischen 60s und 86400s).
3. Microservice erzeugt eine kryptografisch signierte URL für `PUT /bucket/key` mit definierter Gültigkeit.
4. Client führt einen direkten HTTP `PUT` Request gegen die signierte URL aus.

### 2.3 Download-Workflow (Pre-Signed GET)
1. Client fordert temporäre URL an: `POST /api/v1/storage/presigned-download`.
2. Microservice generiert signierte URL mit optionalem Header `response-content-disposition`, um beim Download den korrekten Originaldateinamen zu erzwingen.
3. Client ruft die Datei direkt vom Objektspeicher ab.

---

## 3. Kompatibilitäts-Matrix der Speicheranbieter

| Anbieter | Protokoll | Adressierung | Egress-Kosten | Besonderheiten und Konfiguration |
| :--- | :--- | :--- | :--- | :--- |
| **AWS S3** | S3 API (SigV4) | Virtual-Hosted / Path | Standard AWS Tarife | Referenzimplementierung, Regionen weltweit, strikte Bucket-Policies |
| **Cloudflare R2** | S3-kompatibel | Path / Custom Domain | 0,00 USD (Kostenlos) | Ideal für VibeCore Dokumentenablage. Endpoint: `<accountid>.r2.cloudflarestorage.com`. Region: `auto` oder `weur`. Keine Egress-Gebühren |
| **MinIO** | S3-kompatibel | Path-Style (`addressing_style="path"`) | 0,00 USD (Self-Hosted) | Perfekt für lokale Entwicklung, On-Premise und Air-Gapped Betrieb. Erfordert `STORAGE_ADDRESSING_STYLE=path` |
| **Wasabi** | S3-kompatibel | Virtual-Hosted / Path | 0,00 USD (Fair Use) | Günstige Cloud-Alternative. Regionale Endpunkte z. B. `s3.eu-central-1.wasabisys.com` |

---

## 4. Vier-Säulen-Validierung und Enterprise-Resilienz

### Säule 1: Resilienz und Netzwerkstabilität
* **Timeouts:** Feste Verbindungs-Timeouts (5 Sekunden Connect, 30 Sekunden Read).
* **Automatischer Retry:** Konfigurierter Exponential-Backoff (Standard: 3 Versuche) bei vorübergehenden Verbindungsabbrüchen (`EndpointConnectionError`, `ConnectTimeoutError`).
* **Entkopplung:** Durch Pre-Signed URLs führt ein temporärer Microservice-Ausfall nicht zum Abbruch laufender Großdatei-Transfers.

### Säule 2: Datenintegrität und Transaktionen
* **SHA-256 Prüfsummen:** Beim Direkt-Upload wird der SHA-256 Hash im Stream blockweise berechnet und in den S3-Objektmetadaten (`x-amz-meta-sha256`) dauerhaft persistiert.
* **Metadaten-Verifikation:** Dateigröße, MIME-Typ, ETag und SHA-256 werden vor der Rückgabe formal validiert.

### Säule 3: Sicherheit und Zugriffsschutz
* **API-Key Authentifizierung:** Sämtliche Adapter-Endpunkte werden durch den Header `X-API-Key` geschützt.
* **Content-Type Whitelist:** Strikte Ablehnung gefährlicher Dateitypen (z. B. `.exe`, `.sh`). Freigabe nur für geschäftsrelevante Belege (PDF, PNG, JPEG, TIFF, XML, JSON, CSV).
* **Pfadsicherheit:** UUID-basierte Speicherpfade verhindern Directory-Traversal Angriffe (`../../etc/passwd`).

### Säule 4: Observability und Dauerbetrieb
* **Korrelations-ID:** Lückenlose Weitergabe und Protokollierung des Headers `X-Correlation-ID`.
* **Strukturiertes Logging:** JSON-kompatible Protokolle ohne Speicherung von Geheimnissen oder S3-Keys.
* **Healthchecks:**
  * `GET /health`: Liveness-Check des Containers.
  * `GET /ready`: Readiness-Check mit aktiver Prüfung der Erreichbarkeit des Ziel-Buckets (`HeadBucket`).
