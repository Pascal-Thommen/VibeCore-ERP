# ADR 0011: Bancard vPOS and Catastro QR Adapter Boundary

**Status:** ACCEPTED
**Date:** 2026-10-15

## Context

Paraguayan electronic commerce and payment processing relies heavily on Bancard (vPOS 2.0 and Catastro QR in PYG).
The Finance Core requires verifiable transaction facts for double-entry ledger bookings without coupling the core schema to Bancard API specifics, credit card tokenization, iframe lifecycles, or external webhook retry mechanisms.

## Decision

The Bancard Payment Adapter (VibeCore Pay Bancard) is implemented as an isolated microservice container operating strictly outside the Finance Core:

1. **Isolation & Connectivity:**
   - Direct PostgreSQL access is forbidden.
   - Core and downstream services (such as VibeCore AIBill) communicate with the adapter exclusively through typed REST APIs and HMAC-SHA256 signed webhooks (`X-VibeCore-Signature`).
   - The adapter exposes an OpenAPI specification (`openapi.json`) and `.ai/adapter_schema.md`.

2. **Cryptographic Standards:**
   - Adheres strictly to the Bancard vPOS 2.0 specification:
     - `single_buy`: MD5 token calculation over `private_key + shop_process_id + amount + currency`.
     - `rollback`: MD5 token calculation over `private_key + shop_process_id + "rollback" + "0.00"`.
     - `charge`: MD5 token over `private_key + shop_process_id + "charge" + amount + currency + alias_token`.
     - `confirm_payment`: Constant-time signature verification for Bancard webhook callbacks.

3. **Catastro QR (Paraguay):**
   - Implements EMVCo Merchant-Presented Mode dynamic QR code generation in Guaranies (PYG, code 600) with CRC16-CCITT checksum calculation.
   - Provides status polling and webhook receivers for QR payments.

4. **Resilience, Idempotency & Observability:**
   - All state-changing payment endpoints mandate unique idempotency keys to eliminate duplicate transactions.
   - Transactions follow an explicit persistent state machine (`PENDING`, `APPROVED`, `REJECTED`, `REVERSED`) with audit trails.
   - Outbound webhooks implement exponential backoff retry policies and persistent dead-letter queuing.
   - Observability is ensured via `/healthz`, structured JSON logging with correlation IDs, and Prometheus metrics (`/metrics`).

## Consequences

- The Finance Core remains headless, minimal, and invariant.
- Payment provider secrets and failures are completely isolated from accounting records.
- Consuming services receive deterministic, tamper-proof payment notifications.
