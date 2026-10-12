# WhatsApp Cloud API Adapter Contract

## Adapter identity

- **Name:** whatsapp-cloud-api
- **Version:** 0.1.0
- **Owner:** Shell and Authentication Team
- **OpenAPI:** openapi.json

## Core contract

- **Inbound endpoints/events:**
  - `POST /api/v1/messages/send-template`: Send pre-approved Meta WhatsApp templates (authentication, OTP, customer notifications).
  - `POST /api/v1/messages/send-text`: Send free-form text messages inside the 24-hour customer service window.
  - `POST /api/v1/otp/send`: Generate a cryptographically secure OTP and transmit it via WhatsApp.
  - `POST /api/v1/otp/verify`: Validate a submitted OTP for Single Sign-On (SSO) and user authentication.
  - `GET /api/v1/service-window/{phone_number}`: Query active status of the 24-hour customer service window.
  - `GET /api/v1/webhook`: Meta Hub challenge verification endpoint.
  - `POST /api/v1/webhook`: Meta WhatsApp Cloud API incoming messages and delivery status updates.
- **Outbound endpoints/events:**
  - Outbound Meta Graph API calls (`https://graph.facebook.com/{version}/{phone_number_id}/messages`).
  - Webhook dispatch events to Core/Shell subscribers for message receipt and delivery receipts (sent, delivered, read, failed).
- **Authentication:**
  - External Meta webhooks: Validated with `hub.verify_token` on challenge and `X-Hub-Signature-256` HMAC-SHA256 signature using `META_APP_SECRET`.
  - Internal API callers: Bearer token / asymmetric client authorization.
- **Idempotency key:** Header `Idempotency-Key` or field `idempotency_key` in request body.
- **Correlation ID:** Header `X-Correlation-ID` or field `correlation_id` in request body.
- **Retry and recovery:**
  - Meta Cloud API requests retry with exponential backoff on HTTP 429 and 5xx errors.
  - Webhook receipts acknowledge Meta immediately with HTTP 200 to prevent redundant redelivery.

## Payload evolution

All JSON payloads accept optional `meta` and `custom_data` objects for forward and backward compatibility.
Versioned endpoints use `/api/v1/`. Required fields, error schemas, and response formats are defined in `openapi.json`.

## Security boundary

This adapter has no direct PostgreSQL access. Database isolation is absolute.
Required secrets:
- `META_ACCESS_TOKEN`: Meta Graph API System User / Access Token.
- `META_PHONE_NUMBER_ID`: WhatsApp Business Account phone number identifier.
- `META_APP_SECRET`: App secret for HMAC-SHA256 signature validation of webhooks.
- `META_WEBHOOK_VERIFY_TOKEN`: Verification token for Meta webhook subscription challenge.

Secrets are injected via environment variables or protected Docker secret files (`/run/secrets/`).
Key rotation is performed by updating the secret file or environment variable without requiring application rebuild.
