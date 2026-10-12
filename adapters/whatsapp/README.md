# WhatsApp Cloud API Adapter

Isolated microservice adapter connecting VibeCore ERP and the Shell to the Meta WhatsApp Cloud API.

## Features

1. **Meta WhatsApp Cloud API Client**:
   - Outbound pre-approved template messages (authentication OTP, transaction alerts, notifications).
   - Free-form text messages within the active 24-hour customer service window.
   - Support for Meta's free virtual test numbers (sandbox mode).

2. **Webhook Verification and Event Ingestion**:
   - Automatic GET verification of Meta Hub Challenge tokens (`hub.mode=subscribe`, `hub.verify_token`, `hub.challenge`).
   - HMAC-SHA256 signature verification via `X-Hub-Signature-256` using `META_APP_SECRET`.
   - Real-time ingestion of customer messages (which opens and refreshes the 24-hour service window).
   - Message delivery status tracking (sent, delivered, read, failed).

3. **Single Sign-On (SSO) OTP Logic**:
   - Cryptographically secure 6-digit OTP generation using Python `secrets`.
   - Salted SHA-256 hashing so raw codes are never stored in memory in plaintext.
   - Configurable expiration time-to-live (default 300 seconds / 5 minutes).
   - Attempt-limiting (lockout after 3 invalid attempts).
   - Rate limiting cooldown (60 seconds per phone number).
   - Single-use consumption (replay protection).

## Architecture and Contract

- Complies with VibeCore ERP adapter guidelines (`.ai/adapter_schema.md`).
- Fully isolated service: zero direct database access to PostgreSQL.
- Exposes OpenAPI 3.1 contract in `openapi.json`.
- All cross-boundary JSON payloads support `meta` and `custom_data` objects for forward compatibility.

## API Endpoints

- `GET /health` or `GET /api/v1/health`: Liveness probe.
- `GET /ready` or `GET /api/v1/ready`: Readiness probe.
- `GET /api/v1/webhook`: Meta Webhook Hub Challenge verification.
- `POST /api/v1/webhook`: Meta Webhook event and status receiver.
- `POST /api/v1/messages/send-template`: Send approved WhatsApp template message.
- `POST /api/v1/messages/send-text`: Send text message (checks 24-hour window).
- `POST /api/v1/otp/send`: Generate and send OTP via WhatsApp.
- `POST /api/v1/otp/verify`: Verify submitted OTP code.
- `GET /api/v1/service-window/{phone_number}`: Check 24-hour customer service window status.

## Configuration

Set via environment variables or Docker secrets:

- `WHATSAPP_META_PHONE_NUMBER_ID`: WhatsApp Phone Number ID (e.g. Meta test number).
- `WHATSAPP_META_ACCESS_TOKEN`: Meta System User access token.
- `WHATSAPP_META_APP_SECRET`: Meta App Secret for webhook HMAC verification.
- `WHATSAPP_META_WEBHOOK_VERIFY_TOKEN`: Verification token matching Meta webhook settings.
- `WHATSAPP_META_TEST_MODE`: Set to `true` for local development and Meta test numbers without live credentials.
- `WHATSAPP_OTP_DEFAULT_EXPIRY_SECONDS`: TTL for generated OTPs (default: 300).
- `WHATSAPP_OTP_MAX_ATTEMPTS`: Allowed attempts before invalidation (default: 3).

## Testing

Run tests with pytest:

```bash
pytest
```
