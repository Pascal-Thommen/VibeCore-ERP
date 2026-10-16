# Bancard Adapter Contract

**Status:** IMPLEMENTED
**Adapter Name:** vibecore-pay-bancard
**Version:** 1.0.0
**Owner:** VibeCore Architecture Team
**OpenAPI:** `openapi.json`

The Bancard adapter follows [ADR 0011](../../.ai/adr/0011-bancard-vpos-adapter-boundary.md).
It provides turnkey integration with Bancard vPOS 2.0 (credit/debit cards), card tokenization (Catastro de tarjetas), and Paraguayan dynamic Catastro QR payments in Guaranies (PYG).

## Inbound Operations (Core / Client -> Adapter)

- `POST /api/v1/payments/single-buy`: Initialize single checkout with Bancard process token.
- `POST /api/v1/payments/charge`: Tokenized recurring/1-click charge using `alias_token`.
- `POST /api/v1/payments/cards/new`: Card catastro registration initialization.
- `POST /api/v1/payments/{shop_process_id}/rollback`: Reversal of pending or approved payment.
- `GET /api/v1/payments/{shop_process_id}`: Query transaction state and audit trail.
- `POST /api/v1/qr/generate`: Generate dynamic EMVCo QR code for Paraguayan market.
- `GET /api/v1/qr/{shop_process_id}/status`: Polling status for QR transactions.
- `POST /api/v1/payments/webhook/bancard`: Bancard confirmation callback receiver.
- `GET /api/v1/webhooks/dead-letter`: List un-deliverable downstream webhooks.
- `POST /api/v1/webhooks/dead-letter/{id}/retry`: Re-trigger dead letter delivery.

## Outbound Events (Adapter -> Downstream Services: AIBill / Core)

Events are dispatched via HTTP POST with `X-VibeCore-Signature` (HMAC-SHA256) and `X-VibeCore-Timestamp`:
- `payment.bancard.approved`: Payment successfully settled and authorized.
- `payment.bancard.rejected`: Payment declined by issuer or processor.
- `payment.bancard.reversed`: Payment reversed via rollback.

## Security Boundary

This adapter has NO direct PostgreSQL access. All secrets (`BANCARD_PRIVATE_KEY`, `BANCARD_PUBLIC_KEY`, `VIBECORE_WEBHOOK_SECRET`) are injected via environment variables.
Sensitive cardholder data never touches this service (hosted iframe / redirect flow).
Incoming Bancard confirmation signatures are validated using constant-time comparison.
Outgoing webhooks are cryptographically signed.
Idempotency keys protect all mutative endpoints against double-charging.
