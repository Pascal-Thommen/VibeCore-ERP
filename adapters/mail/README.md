# VibeCore Mail Microservice Adapter

Leichtgewichtiger, autonomer E-Mail-Microservice in Go für das VibeCore ERP Ökosystem. Der Dienst kapselt den gesamten E-Mail-Verkehr (SMTP Versand, IMAP Empfang via IDLE, Inbound Webhooks und Parsing) hinter einer einheitlichen, zustandslosen REST-API mit lokaler ACID-Persistenz.

## Die 7 Kernbausteine

1. **SMTP Versand:** Standardkonformer Versand über externe Provider oder eigene Server via `go-mail` mit TLS, STARTTLS und Authentifizierung.
2. **IMAP Empfang & IDLE:** Abruf von Postfächern inklusive IMAP IDLE für sofortige Benachrichtigungen via `go-imap/v2`.
3. **Inbound Webhooks:** HTTP POST Endpunkte zur strukturierten Annahme von E-Mails externer Anbieter (Resend, Brevo, SendGrid, Generic).
4. **Attachment Handling:** Robustes MIME-Parsing zum Extrahieren eingehender Belege (PDFs, Bilder) mit SHA-256 Checksummen und sicheres Anhängen ausgehender Dokumente.
5. **Template Engine:** Sicheres Rendern dynamischer Vorlagen für HTML und Text via Go Standardbibliothek (`html/template`) mit automatischem XSS-Schutz.
6. **Queue und Retry Logik:** Lokale, persistente Warteschlange (`bbolt`) mit exponentiellem Backoff und Dead-Letter-Queue bei Verbindungsproblemen (Zero-Mock-Resilienz).
7. **Status Tracking & Dispatching:** Protokollierung aller Zustellereignisse und HMAC-signierte Webhook-Weiterleitung an aufrufende VibeCore Module.

## Endpunkte

| Methode | Pfad | Authentifizierung | Beschreibung |
|---|---|---|---|
| `POST` | `/api/v1/mail/send` | `X-API-Key` | E-Mail asynchron und persistent in die Warteschlange einreihen |
| `GET` | `/api/v1/mail/status/{id}` | `X-API-Key` | Zustellungsstatus und Fehlerprotokoll einer E-Mail abrufen |
| `GET` | `/api/v1/mail/templates` | `X-API-Key` | Liste aller registrierten Vorlagen abrufen |
| `POST` | `/api/v1/mail/templates` | `X-API-Key` | Neues dynamisches Template registrieren |
| `POST` | `/api/v1/mail/webhooks/resend` | Öffentlich | Resend Inbound- und Status-Webhook |
| `POST` | `/api/v1/mail/webhooks/brevo` | Öffentlich | Brevo Zustell- und Bounce-Webhook |
| `POST` | `/api/v1/mail/webhooks/sendgrid` | Öffentlich | SendGrid Event- und Inbound-Parse-Webhook |
| `POST` | `/api/v1/mail/webhooks/generic` | Öffentlich | Universelle Annahme von RFC 822 / Raw MIME oder JSON |
| `GET` | `/health` | Öffentlich | Liveness Healthcheck |
| `GET` | `/ready` | Öffentlich | Readiness Healthcheck mit Datenbank- und SMTP-Verbindungstest |
| `GET` | `/metrics` | Öffentlich | Laufzeit-Metriken (Speicherverbrauch in MB, Queues, Goroutines) |

## Konfiguration

Die Konfiguration erfolgt vollständig über Umgebungsvariablen oder eine `.env`-Datei:

```bash
# Basis
PORT=8025
MAIL_API_KEY=dein-geheimer-api-schluessel-mindestens-32-zeichen

# SMTP
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USERNAME=resend
SMTP_PASSWORD=dein-smtp-passwort
SMTP_FROM_EMAIL=rechnungen@vibecore.py
SMTP_FROM_NAME="VibeCore ERP"
SMTP_TLS_POLICY=opportunistic

# IMAP
IMAP_ENABLED=false
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USERNAME=postfach@vibecore.py
IMAP_PASSWORD=app-passwort
IMAP_IDLE_ENABLED=true

# Queue & Resilienz
QUEUE_DB_PATH=/data/mail_queue.db
QUEUE_MAX_RETRIES=5
QUEUE_BASE_BACKOFF=2s
QUEUE_MAX_BACKOFF=60s

# Event Webhooks
STATUS_WEBHOOK_URL=http://localhost:8000/api/v1/adapters/mail/events
STATUS_WEBHOOK_SECRET=webhook-signatur-geheimnis
```

## Lokale Ausführung & Container

Mit Docker Compose starten:

```bash
docker compose up -d --build
```

Lokal mit Go starten:

```bash
go run ./cmd/server
```

## Tests ausführen

Die gesamte Testsuite inklusive End-to-End-SMTP-Simulation, Inflight-Recovery, Idempotenz und Race-Detector ausführen:

```bash
go test -v -race ./...
```

## Ressourcenverbrauch & Benchmark

Das System wurde gezielt auf minimalen Ressourcenverbrauch optimiert:
* **Allokierter Speicher:** ~0.85 MB RAM im Ruhezustand.
* **Heap In-Use:** ~2.10 MB RAM.
* **Akzeptanzkriterium:** Weit unter der Grenze von 20 MB RAM.
* **Docker Image:** Stufenloser Multi-Stage Build (< 25 MB Imagegröße).

## Weiterführende Dokumentation

* [Forschungsdossier & Architekturentscheidung](RESEARCH_DOSSIER.md)
* [Adapter-Schema Vertrag](.ai/adapter_schema.md)
* [OpenAPI 3.1 Spezifikation](openapi.json)
