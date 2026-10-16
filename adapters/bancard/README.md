# VibeCore Pay: Bancard vPOS 2.0 & Catastro QR Microservice

Isolated payment gateway adapter for Paraguay under the VibeCore ecosystem, compliant with [ADR 0011](../../.ai/adr/0011-bancard-vpos-adapter-boundary.md) and the 4-Pillar Testing & Architecture Standard.

## Architecture & Capabilities

1. **Bancard vPOS 2.0 Protocol Implementation:**
   - Single Buy checkout initialization (`single_buy`): Calculates cryptographic MD5 token over `private_key + shop_process_id + amount + currency`.
   - Card Catastro (`cards/new`): Generates process identifier for secure card registration iframe.
   - Token Charge (`charge`): Tokenized 1-click and subscription billing via customer `alias_token`.
   - Rollback / Reversal (`rollback`): Instant cancellation of payments via signed rollback tokens.
   - Confirmation Webhook (`confirm_payment`): Constant-time signature verification for Bancard transaction callbacks.

2. **Catastro QR (Paraguayan Instant Payment System):**
   - Generates compliant EMVCo Merchant-Presented Mode dynamic QR codes for Guaranies (PYG, code 600).
   - Dynamic CRC16-CCITT checksum validation.
   - Generates high-resolution PNG data URIs via `segno`.
   - Dual settlement support: Polling query endpoint and real-time webhook callback receiver.

3. **Resilience, Idempotency & Booking Safety:**
   - Strict `Idempotency-Key` enforcement across all payment initialization and charge routes.
   - Durable ACID transaction state machine (`PENDING`, `APPROVED`, `REJECTED`, `REVERSED`) with audit history.
   - Downstream Webhook Dispatcher: Sends HMAC-SHA256 signed notifications (`X-VibeCore-Signature`) to VibeCore AIBill and ERP with exponential backoff retries and dead-letter queue persistence.

4. **Observability:**
   - Healthcheck endpoints (`/healthz`, `/health`, `/ready`) checking database and service status.
   - Prometheus metrics endpoint (`/metrics`) exposing transaction latencies, payment method distribution, and dead-letter size.
   - Structured JSON logging with correlation IDs.

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `BANCARD_ENVIRONMENT` | `staging` | `staging` or `production` |
| `BANCARD_PUBLIC_KEY` | `test_public_key` | Bancard commerce public key |
| `BANCARD_PRIVATE_KEY` | `test_private_key` | Bancard commerce private key |
| `BANCARD_STAGING_URL` | `https://vpos.infonet.com.py:8888` | Bancard staging gateway URL |
| `BANCARD_PROD_URL` | `https://vpos.infonet.com.py` | Bancard production gateway URL |
| `VIBECORE_WEBHOOK_SECRET` | `vibecore_webhook_secret_key` | Secret used to sign downstream webhooks |
| `DOWNSTREAM_WEBHOOK_URLS` | `[]` | JSON array of target webhook URLs (e.g. AIBill) |
| `DATABASE_URL` | `sqlite:///./bancard_pay.db` | Persistence connection string |
| `REQUEST_TIMEOUT_SECONDS` | `10.0` | Gateway HTTP timeout |
