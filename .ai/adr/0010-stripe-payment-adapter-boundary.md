# ADR 0010: Stripe Payment Adapter Boundary and Gateway Architecture

**Status:** ACCEPTED
**Date:** 2026-10-15

## Context

Internationaler Zahlungsverkehr erfordert die Anbindung an globale Zahlungsdienstleister wie Stripe (Kreditkarten, Apple Pay, Google Pay, SEPA, internationale Zahlungsmethoden).
Der VibeCore Finance Core muss frei von spezifischen Gateway-Schnittstellen, externen Hashing-Algorithmen und flüchtigen Netzwerk-Timeouts bleiben.
Gleichzeitig muss der Stripe Adapter derselben Schnittstellenlogik wie der Pagopar Adapter folgen, um einen nahtlosen Parallelbetrieb (Multi-Gateway) im ERP zu gewährleisten.

## Decision

1. Der Stripe Gateway Adapter wird als eigenständiger, isolierter Microservice außerhalb des Finance Core betrieben (`adapters/stripe`).
2. Der Adapter besitzt keinen direkten Datenbankzugriff auf PostgreSQL. Die Kommunikation mit dem Core erfolgt über authentifizierte REST-APIs und signierte Webhooks.
3. Der Adapter verwaltet ein eigenes lokales Transaktions-Log (SQLite / PostgreSQL) zur Sicherstellung von Idempotenz und lückenloser Nachvollziehbarkeit aller Zahlungsstatus-Änderungen.
4. Kryptografische Signaturprüfung von Webhooks erfolgt zwingend mit zeitkonstantem String-Vergleich (`hmac.compare_digest`) auf Basis von HMAC-SHA256 mit Timestamp-Toleranzprüfung gegen Replay-Angriffe.
5. Beträge werden gemäß der Cent-Betragslogik von Stripe in die kleinste Währungseinheit umgerechnet, wobei Zero-Decimal-Währungen berücksichtigt werden.
6. Bei Ausbleiben von Webhooks wird ein aktiver Polling-Mechanismus (`/api/v1/stripe/payments/{payment_id}/sync`) als Ausfallabsicherung bereitgestellt.
7. Konfiguration erfolgt ausschließlich über Umgebungsvariablen (`STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `ADAPTER_API_KEY`, `STRIPE_DEFAULT_CURRENCY`).

## Consequences

* Der Finance Core bleibt schlank, immutable und unabhängig von Drittanbieter-Ausfällen.
* Transiente Netzwerkstörungen bei Stripe werden durch Timeouts, Retries und Polling im Adapter abgefangen.
* Webhook-Wiederholungen führen niemals zu doppelten Buchungen im ERP.
* ERP-Module können flexibel zwischen lokalem Pagopar und internationalem Stripe Gateway routen.
