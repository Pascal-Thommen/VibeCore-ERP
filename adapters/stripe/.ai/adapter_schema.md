# Adapter Schema: Stripe Payment Gateway

## Adapter identity

* **Name:** `stripe-payment-adapter`
* **Version:** `1.0.0`
* **Owner:** VibeCore ERP Core Team (Integration & Payments)
* **OpenAPI:** `openapi.json`

## Core contract

* **Inbound endpoints (Core to Adapter / Public Callback):**
  * `POST /api/v1/stripe/checkout-sessions`: Erstellung einer Stripe Checkout-Session mit Zahlungs-URL.
  * `POST /api/v1/stripe/payment-intents`: Direkte Initiierung von Zahlungen über Stripe PaymentIntents.
  * `POST /api/v1/stripe/webhook`: Asynchrone Zahlungsbenachrichtigung von Stripe (Callback).
  * `POST /api/v1/stripe/payments/{payment_id}/sync`: Polling zur Zustandskonsolidierung bei ausbleibendem Webhook.
  * `GET /api/v1/stripe/payments/{payment_id}`: Abruf des Transaktionsstatus und Audit-Logs (per VibeCore Order-ID oder Stripe ID).
  * `GET /health`: Healthcheck für Liveness-Probe.
  * `GET /ready`: Readiness-Probe mit Prüfung der internen Datenbank und Konfiguration.

* **Outbound endpoints (Adapter zu Stripe / Adapter zu Core):**
  * Stripe REST API `POST https://api.stripe.com/v1/checkout/sessions`: Erzeugung gehosteter Bezahlseiten.
  * Stripe REST API `POST https://api.stripe.com/v1/payment_intents`: Erzeugung direkter PaymentIntents.
  * Stripe REST API `GET https://api.stripe.com/v1/payment_intents/{id}` und `GET https://api.stripe.com/v1/checkout/sessions/{id}`: Status-Polling.
  * Standardisierte Event-Benachrichtigungen zum VibeCore Finance Core (`payment.succeeded`, `payment.failed`).

* **Authentication:**
  * Interne Endpunkte (`/checkout-sessions`, `/payment-intents`, `/payments/{payment_id}`, `/sync`): API-Key über Header `X-Adapter-Key` oder Bearer Token.
  * Webhook-Endpunkt (`/webhook`): Kryptografische Signaturprüfung via HMAC-SHA256 (`Stripe-Signature` Header mit Timestamp `t` und Signatur `v1` gegen `STRIPE_WEBHOOK_SECRET`).

* **Idempotency key:**
  * Header `X-Idempotency-Key` bei Erstellung von Checkout-Sessions und PaymentIntents (wird als `Idempotency-Key` an Stripe durchgereicht).
  * Stripe Event ID (`evt_...`) und PaymentIntent-/Session-ID bei Webhook-Verarbeitung zur Verhinderung von Doppelbuchungen.

* **Correlation ID:**
  * Header `X-Correlation-ID` wird durchgängig von allen Endpunkten mitgeführt, in Logs protokolliert und in HTTP-Headern zurückgegeben.

* **Retry and recovery:**
  * Stripe API Aufrufe: Automatischer Retry mit Exponential Backoff bei transienten 5xx Fehlern und Verbindungsabbrüchen (HTTPX Client).
  * Polling (`/payments/{payment_id}/sync`): Dient als Recovery-Mechanismus bei Netzwerkverlusten und Webhook-Ausfällen.

## Payload evolution

Alle JSON Payloads unterstützen optionale `meta` und `custom_data` Felder für zukünftige Erweiterungen.
Fehlerantworten folgen dem RFC 7807 Standard (`application/problem+json`) mit standardisierten Fehlercodes (`VALIDATION_ERROR`, `SIGNATURE_MISMATCH`, `GATEWAY_TIMEOUT`, `ORDER_NOT_FOUND`).

## Security boundary

Dieser Adapter besitzt keinerlei direkten Zugriff auf die PostgreSQL Hauptdatenbank des VibeCore ERP.
Benötigte Umgebungsvariablen:
* `STRIPE_SECRET_KEY`: Geheimer API-Schlüssel für Stripe REST API Aufrufe.
* `STRIPE_PUBLISHABLE_KEY`: Öffentlicher Händlerschlüssel für Frontend-Integrationen.
* `STRIPE_WEBHOOK_SECRET`: Geheimer Schlüssel (`whsec_...`) zur HMAC-SHA256 Signaturprüfung eingehender Webhooks.
* `ADAPTER_API_KEY`: Sicherung der internen Adapter-Schnittstellen.
* `STRIPE_DEFAULT_CURRENCY`: Standardwährung des Händlers (z. B. `USD`, `EUR`).
* `STRIPE_ENV`: Ausführungsumgebung (`sandbox` oder `production`).

Schlüsselrotation erfolgt durch Aktualisierung der Container-Umgebungsvariablen im Secrets-Manager ohne Codeänderung.
