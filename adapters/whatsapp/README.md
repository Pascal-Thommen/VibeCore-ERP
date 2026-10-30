# VibeCore WhatsApp Cloud API Microservice Adapter

Schlanker, isolierter Microservice-Adapter zur Anbindung der Meta WhatsApp Cloud API fuer OTP-Authentifizierung und Template-Benachrichtigungen.

## Kernfunktionen

1. **Meta WhatsApp Cloud API Client (`app/client.py`)**:
   - Asynchroner Versand freigegebener WhatsApp-Templates (`POST /api/v1/messages/send-template`) ueber `httpx.AsyncClient` mit expliziten Timeouts.
2. **Kryptografischer OTP-Service (`app/otp.py`)**:
   - Generierung 6-stelliger numerischer Einmalpasswoerter mit `secrets`, gesalzene SHA-256 Speicherung, Cooldown-Ratenbegrenzung, Ablaufpruefung (TTL), Versuchsbegrenzung (Lockout) und Replay-Schutz (`POST /api/v1/otp/send`, `POST /api/v1/otp/verify`).
3. **Webhook-Verifikation & Zustellstatus (`app/webhook.py`)**:
   - `GET /api/v1/webhook` fuer Meta Hub Challenge (`hub.mode=subscribe`, `hub.verify_token`, `hub.challenge`).
   - `POST /api/v1/webhook` mit verpflichtender `X-Hub-Signature-256` HMAC-SHA256 Signaturpruefung.

## Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/health` | Liveness Healthcheck |
| `GET` | `/ready` | Readiness Check der Meta-Konfiguration |
| `GET` | `/api/v1/webhook` | Meta Hub Challenge Verifikation |
| `POST` | `/api/v1/webhook` | Signierter Empfang von Zustellstatus-Updates (`X-Hub-Signature-256`) |
| `POST` | `/api/v1/messages/send-template` | Versand von WhatsApp-Template-Nachrichten |
| `POST` | `/api/v1/otp/send` | OTP erzeugen und via WhatsApp-Template versenden |
| `POST` | `/api/v1/otp/verify` | OTP-Code zeitkonstant verifizieren |
