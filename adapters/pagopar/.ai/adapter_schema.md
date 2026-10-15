# Adapter Schema: Pagopar Payment Gateway

## Adapter identity

* **Name:** `pagopar-payment-adapter`
* **Version:** `1.0.0`
* **Owner:** VibeCore ERP Core Team (Integration & Payments)
* **OpenAPI:** `openapi.json`

## Core contract

* **Inbound endpoints (Core to Adapter / Public Callback):**
  * `POST /api/v1/pagopar/orders`: Initiierung einer Zahlungstransaktion mit Pagopar.
  * `POST /api/v1/pagopar/webhook`: Asynchrone Zahlungsbenachrichtigung von Pagopar (Callback).
  * `POST /api/v1/pagopar/orders/{order_id}/sync`: Polling zur Zustandskonsolidierung bei ausbleibendem Webhook.
  * `GET /api/v1/pagopar/orders/{order_id}`: Abruf des Transaktionsstatus und Audit-Logs.
  * `GET /health`: Healthcheck für Liveness-Probe.
  * `GET /ready`: Readiness-Probe mit Prüfung der internen Datenbank und Konfiguration.

* **Outbound endpoints (Adapter zu Pagopar / Adapter zu Core):**
  * Pagopar API v2 `POST /api/comercios/2.0/iniciar-transaccion`: Erzeugung des Zahlungs-Auftrags.
  * Pagopar API v1.1 `POST /api/pedidos/1.1/traer`: Status-Polling bei Unklarheiten.
  * Optionaler Event-Forwarder zum VibeCore Finance Core (`payment.succeeded`, `payment.failed`).

* **Authentication:**
  * Interne Endpunkte (`/orders`, `/sync`): API-Key über Header `X-Adapter-Key` oder Bearer Token.
  * Webhook-Endpunkt (`/webhook`): Kryptografische Signaturprüfung via SHA-1 Hash (`resultado[0].token == sha1(private_key + hash_pedido)`).

* **Idempotency key:**
  * Header `X-Idempotency-Key` bei Auftragserstellung (`/orders`).
  * `hash_pedido` und `identificador_pago` bei Webhook-Verarbeitung zur Verhinderung von Doppelbuchungen.

* **Correlation ID:**
  * Header `X-Correlation-ID` wird durchgängig von allen Endpunkten mitgeführt und in Logs protokolliert.

* **Retry and recovery:**
  * Pagopar API Aufrufe: Automatischer Retry mit Exponential Backoff bei transienten 5xx Fehlern und Verbindungsabbrüchen.
  * Polling (`/sync`): Dient als Recovery-Mechanismus bei Netzwerkverlusten und Webhook-Ausfällen.

## Payload evolution

Alle JSON Payloads unterstützen optionale `meta` und `custom_data` Felder für zukünftige Erweiterungen.
Fehlerantworten folgen dem RFC 7807 Standard (`application/problem+json`) mit standardisierten Fehlercodes (`VALIDATION_ERROR`, `SIGNATURE_MISMATCH`, `GATEWAY_TIMEOUT`, `ORDER_NOT_FOUND`).

## Security boundary

Dieser Adapter besitzt keinerlei direkten Zugriff auf die PostgreSQL Hauptdatenbank des VibeCore ERP.
Benötigte Umgebungsvariablen:
* `PAGOPAR_PUBLIC_KEY`: Öffentlicher Händlerschlüssel.
* `PAGOPAR_PRIVATE_KEY`: Geheimer kryptografischer Schlüssel.
* `PAGOPAR_ENV`: Umgebung (`sandbox` oder `production`).
* `PAGOPAR_BASE_URL`: Basis-URL der Pagopar REST API.
* `ADAPTER_API_KEY`: Sicherung der internen Adapter-Schnittstellen.

Schlüsselrotation erfolgt durch Aktualisierung der Container-Umgebungsvariablen im Secrets-Manager ohne Codeänderung.
