# VibeCore Stripe Payment Gateway Microservice

Autonomer, wiederverwendbarer Microservice für den internationalen Zahlungsdienstleister Stripe im VibeCore ERP Ökosystem gemäß ADR 0008 und ADR 0010.

## Kernfunktionen

1. **Stripe Checkout Sessions (Gehostete Zahlungsseite):**
   * Vollwertige Anbindung an Stripe Checkout (`POST /v1/checkout/sessions`).
   * Automatische Erzeugung der kundenindividuellen Checkout-URL (`https://checkout.stripe.com/c/pay/...`).
   * Umrechnung von Beträgen in Cents gemäß Cent-Betragslogik unter Berücksichtigung von Zero-Decimal-Währungen.

2. **Direkte PaymentIntents:**
   * Initiierung direkter Zahlungen (`POST /v1/payment_intents`) für programmatische Workflows.
   * Bereitstellung von `client_secret` für clientseitige Bestätigung.

3. **Kryptografisch gesicherte Webhooks:**
   * Asynchroner Empfang von Zahlungsquittungen (`POST /api/v1/stripe/webhook`).
   * Strikt timing-resistente Signaturvalidierung via HMAC-SHA256 (`hmac.compare_digest`).
   * Timestamp-Toleranzprüfung gegen Replay-Angriffe.
   * Schutz vor manipulierten oder gefälschten Zahlungsbenachrichtigungen.

4. **Idempotenz und Datenintegrität (Zero-Mock-Doktrin):**
   * Lokales, ACID-konformes Transaktions-Log auf SQLite/PostgreSQL-Basis.
   * Verhinderung doppelter Buchungen bei mehrfach eintreffenden Webhooks über Event-ID Deduplizierung.
   * Lückenlose Nachvollziehbarkeit aller Statusübergänge (`INITIATED`, `PENDING_PAYMENT`, `PAID`, `EXPIRED`, `FAILED`, `CANCELLED`).

5. **Resilienz und Polling-Fallback:**
   * Synchronisations-Endpunkt (`POST /api/v1/stripe/payments/{payment_id}/sync`) zur manuellen oder zeitgesteuerten Konsolidierung.
   * Aktive Statusabfrage bei Stripe (`/v1/checkout/sessions/{id}` oder `/v1/payment_intents/{id}`) bei verzögerten Webhooks.
   * Sauberes Timeout- und Retry-Management mit Exponential Backoff bei Verbindungsproblemen.

6. **Observability und Sicherheit:**
   * Keine hardcodierten Secrets: Konfiguration über Umgebungsvariablen (`STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `ADAPTER_API_KEY`).
   * Strukturierte Logs mit durchgängigen Korrelations-IDs (`X-Correlation-ID`).
   * Standardisierte Endpunkte für Orchestrierung: `/health` und `/ready`.

## Schnittstellen und Dokumentation

* **Adapter Schema:** `.ai/adapter_schema.md`
* **OpenAPI 3.1 Spezifikation:** `openapi.json`
* **Recherche- und Spezifikationsdossier:** `DOSSIER_STRIPE_RESEARCH.md`
* **Architekturentscheidung:** `../../.ai/adr/0010-stripe-payment-adapter-boundary.md`

## Betrieb via Docker

```bash
docker build -t vibecore-stripe-adapter .
docker run -p 8000:8000 --env-file .env vibecore-stripe-adapter
```
