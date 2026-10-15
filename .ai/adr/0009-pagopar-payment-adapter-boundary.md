# ADR 0009: Pagopar Payment Adapter Boundary and Gateway Architecture

**Status:** ACCEPTED
**Date:** 2026-10-15

## Context

Paraguayischer Zahlungsverkehr erfordert die Anbindung an lokale Zahlungsdienstleister wie Pagopar (Kredit-/Debitkarten, Bancard, Pago Express, Aqui Pago, SIPAP QR).
Der VibeCore Finance Core muss frei von spezifischen Gateway-Schnittstellen, externen Hashing-Algorithmen und flüchtigen Netzwerk-Timeouts bleiben.

## Decision

1. Der Pagopar Gateway Adapter wird als eigenständiger, isolierter Microservice außerhalb des Finance Core betrieben.
2. Der Adapter besitzt keinen direkten Datenbankzugriff auf PostgreSQL. Die Kommunikation mit dem Core erfolgt über authentifizierte REST-APIs und signierte Webhooks.
3. Der Adapter verwaltet ein eigenes lokales Transaktions-Log zur Sicherstellung von Idempotenz und Nachvollziehbarkeit aller Zahlungsstatus-Änderungen.
4. Cryptografische Signaturprüfung von Webhooks erfolgt zwingend mit zeitkonstantem String-Vergleich (`hmac.compare_digest`) auf Basis von `SHA1(private_key + hash_pedido)`.
5. Bei Ausbleiben von Webhooks wird ein aktiver Polling-Mechanismus (`/api/pedidos/1.1/traer` mit `SHA1(private_key + 'CONSULTA')`) als Ausfallabsicherung bereitgestellt.
6. Konfiguration erfolgt ausschließlich über Umgebungsvariablen (`PAGOPAR_PUBLIC_KEY`, `PAGOPAR_PRIVATE_KEY`, `PAGOPAR_ENV`).

## Consequences

* Der Finance Core bleibt schlank, immutable und unabhängig von Drittanbieter-Ausfällen.
* Transiente Netzwerkstörungen bei Pagopar werden durch Timeouts, Retries und Polling im Adapter abgefangen.
* Webhook-Wiederholungen führen niemals zu doppelten Buchungen im ERP.
