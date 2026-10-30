# WhatsApp Cloud API Adapter Contract

## Adapter identity

- **Name:** vibecore-whatsapp-adapter
- **Version:** 0.1.0
- **Owner:** Shell and Authentication Team
- **OpenAPI:** openapi.json

## Core contract

- **Inbound endpoints/events:**
  - `GET /health`: Liveness check.
  - `GET /ready`: Readiness check validating Meta credentials configuration.
  - `GET /api/v1/webhook`: Meta Hub challenge verification (`hub.mode=subscribe`, `hub.verify_token`, `hub.challenge`).
  - `POST /api/v1/webhook`: Meta WhatsApp Cloud API incoming webhook and delivery status receiver (strictly verified via `X-Hub-Signature-256`).
  - `POST /api/v1/messages/send-template`: Send pre-approved Meta WhatsApp template messages (notifications, alerts, OTP).
  - `POST /api/v1/otp/send`: Generate a cryptographically secure 6-digit OTP and transmit it via WhatsApp Cloud API.
  - `POST /api/v1/otp/verify`: Constant-time verification of a submitted OTP for SSO and user authentication.
- **Outbound endpoints/events:**
  - Outbound Meta Graph API calls (`https://graph.facebook.com/{version}/{phone_number_id}/messages`) with explicit network timeouts.
- **Authentication:**
  - External Meta webhooks: Validated with `hub.verify_token` on challenge and `X-Hub-Signature-256` HMAC-SHA256 signature using `WHATSAPP_META_APP_SECRET`.
- **Retry and recovery:**
  - Explicit 10s HTTP timeout on all Meta Cloud API calls (`504 Gateway Timeout` on timeout, `502 Bad Gateway` on network failure).

## Payload evolution

All cross-boundary JSON payloads support optional `meta` and `custom_data` objects for compatible evolution.

## Security boundary

This adapter is fully isolated and has no direct PostgreSQL access.
Required secrets (`WHATSAPP_META_ACCESS_TOKEN`, `WHATSAPP_META_APP_SECRET`, `WHATSAPP_META_WEBHOOK_VERIFY_TOKEN`) are injected via environment variables or protected Docker secret files (`/run/secrets/`).
