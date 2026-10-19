# Adapter Schema: Mail Microservice Adapter

## Adapter identity

- **Name:** vibecore-mail-adapter
- **Version:** 0.1.0
- **Owner:** VibeCore Infrastructure Team
- **OpenAPI:** openapi.json

## Core contract

- **Inbound endpoints/events:**
  - `POST /api/v1/mail/send`: Asynchroner, persistenter E-Mail-Versand mit Templating, Anhängen und Idempotenz
  - `GET /api/v1/mail/status/{id}`: Abruf des aktuellen Zustellungsstatus und Fehlermeldungen
  - `GET /api/v1/mail/templates`: Auflistung aller verfügbaren E-Mail-Templates
  - `POST /api/v1/mail/templates`: Registrierung neuer dynamischer HTML- und Text-Vorlagen
  - `POST /api/v1/mail/webhooks/resend`: Inbound- und Status-Webhook für Resend
  - `POST /api/v1/mail/webhooks/brevo`: Zustell- und Bounce-Webhook für Brevo (Sendinblue)
  - `POST /api/v1/mail/webhooks/sendgrid`: Inbound Parse- und Event-Webhook für SendGrid
  - `POST /api/v1/mail/webhooks/generic`: Universelle Annahme von RFC 822 / Raw MIME oder strukturiertem JSON
  - `GET /health`: Liveness-Check des Microservice Containers
  - `GET /ready`: Readiness-Check mit Datenbank- und SMTP-Konnektivitätsprüfung
  - `GET /metrics`: Metriken zu Speichernutzung (< 20 MB RAM), Uptime und Warteschlangen
- **Outbound endpoints/events:**
  - SMTP Versand über RFC 5321 (go-mail) mit TLS, STARTTLS und Auth
  - IMAP Abruf über RFC 3501 / RFC 2177 IDLE (go-imap/v2)
  - Webhook Dispatcher an `STATUS_WEBHOOK_URL` (HMAC-SHA256 signiert) zur Echtzeit-Benachrichtigung des VibeCore Core/Shell
- **Authentication:**
  - Service-zu-Service API-Key via Header `X-API-Key` oder `Authorization: Bearer <key>`
  - Signierte Webhooks via HMAC-SHA256 Header `X-VibeCore-Signature`
- **Idempotency key:**
  - `Idempotency-Key` Header bei `POST /api/v1/mail/send`. Verhindert doppelte Versendungen bei Netzwerkunterbrechungen
- **Correlation ID:**
  - `X-Correlation-ID` Header bei allen Inbound- und Outbound-Operationen für lückenloses Tracing
- **Retry and recovery:**
  - Lokale Persistenz in ACID-konformer B+ Tree Datenbank (`bbolt`)
  - Exponentieller Backoff mit konfigurierbarer Basis und Obergrenze
  - Dead Letter Queue (`FAILED`) nach Erreichen der maximalen Fehlversuche
  - Automatische Wiederaufnahme ungeklärter Zustände (`RecoverInflight`) nach Systemneustart oder Absturz

## Payload evolution

Alle JSON-Payloads unterstützen optionale `metadata` und `custom_data` Objekte. Fehlerantworten liefern einheitlich das Schema `ErrorResponse` mit `error` und `message`. Alle Schnittstellen sind abwärtskompatibel.

## Security boundary

Dieser Adapter besitzt keinen direkten Datenbankzugriff auf PostgreSQL des Core. Erforderliche Secrets (`MAIL_API_KEY`, `SMTP_PASSWORD`, `IMAP_PASSWORD`, `STATUS_WEBHOOK_SECRET`) werden ausschließlich über Umgebungsvariablen oder Docker Secrets injiziert. Schlüsselrotation erfolgt ohne Downtime.
