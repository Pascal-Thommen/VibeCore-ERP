# VibeCore Pagopar Payment Gateway Microservice

Autonomer, wiederverwendbarer Microservice für den paraguayischen Zahlungsdienstleister Pagopar im VibeCore ERP Ökosystem gemäß ADR 0008 und ADR 0009.

## Kernfunktionen

1. **Zahlungsinitiierung (Creación de Pedidos):**
   * Vollwertige Anbindung an die Pagopar API v2 (`POST /api/comercios/2.0/iniciar-transaccion`).
   * Kryptografische Token-Berechnung via SHA-1 Hash (`private_key + id_pedido_comercio + str(float(monto_total))`).
   * Automatische Erzeugung der kundenindividuellen Checkout-URL (`https://www.pagopar.com/pagos/{hash}` bzw. Sandbox).

2. **Kryptografisch gesicherte Webhooks (Notificación de Pago):**
   * Asynchroner Empfang von Zahlungsquittungen (`POST /api/v1/pagopar/webhook`).
   * Strikt timing-resistente Signaturvalidierung (`hmac.compare_digest(token_received, sha1(private_key + hash_pedido))`).
   * Schutz vor manipulierten oder gefälschten Zahlungsbenachrichtigungen.

3. **Idempotenz und Datenintegrität (Zero-Mock-Doktrin):**
   * Lokales, ACID-konformes Transaktions-Log auf SQLite/PostgreSQL-Basis.
   * Verhinderung doppelter Buchungen bei mehrfach eintreffenden Webhooks.
   * Lückenlose Nachvollziehbarkeit aller Statusübergänge (`INITIATED`, `PENDING_PAYMENT`, `PAID`, `EXPIRED`, `FAILED`).

4. **Resilienz und Polling-Fallback (Traer Pedido):**
   * Synchronisations-Endpunkt (`POST /api/v1/pagopar/orders/{order_id}/sync`) zur manuellen oder zeitgesteuerten Konsolidierung.
   * Nutzt den Pagopar Polling-Endpunkt (`/api/pedidos/1.1/traer`) mit Abfrage-Token `SHA1(private_key + 'CONSULTA')`.
   * Sauberes Timeout- (10s) und Retry-Management mit Exponential Backoff bei Verbindungsproblemen.

5. **Observability und Sicherheit:**
   * Keine hardcodierten Secrets: Konfiguration über standardisierte Umgebungsvariablen (`PAGOPAR_PUBLIC_KEY`, `PAGOPAR_PRIVATE_KEY`, `PAGOPAR_ENV`).
   * Strukturierte Logs mit durchgängigen Korrelations-IDs (`X-Correlation-ID`).
   * Standardisierte Endpunkte für Orchestrierung: `/health` und `/ready`.

## Schnittstellen und Dokumentation

* **Adapter Schema:** `.ai/adapter_schema.md`
* **OpenAPI 3.1 Spezifikation:** `openapi.json`
* **Recherche- und Spezifikationsdossier:** `DOSSIER_PAGOPAR_RESEARCH.md`

## Betrieb via Docker

```bash
docker build -t vibecore-pagopar-adapter .
docker run -p 8000:8000 --env-file .env vibecore-pagopar-adapter
```
