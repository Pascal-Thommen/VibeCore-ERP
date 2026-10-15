# ADR 0011: Universal Python SDK for Modular Microservice Adapters

**Status:** ACCEPTED
**Date:** 2026-10-15

## Context

Mit der Fertigstellung der Microservice-Adapter für Google Auth (OIDC), S3 Objektspeicher, Pagopar und Stripe benötigt VibeCore eine universelle, typsichere Client-Bibliothek (`sdk/vibecore`).
AI-Agenten und Entwickler dürfen nicht unstrukturierte HTTP-Requests mit inkonsistenter Fehlerbehandlung oder flüchtigen Dictionaries implementieren.
Das SDK muss:
1. Eine strikte Typisierung aller Payloads und Responses über Pydantic v2 bereitstellen.
2. Eine einheitliche VibeCore-Exception-Hierarchie bieten.
3. Resilienz durch konfigurierbare Timeouts und automatische Retries für transiente Fehler (502, 503, 504, Verbindungsabbrüche) garantieren.
4. Rückwärtskompatibilität für den bestehenden CoreClient sicherstellen.

## Decision

1. Das SDK unter `sdk/vibecore` wird modular erweitert:
   * `vibecore.core`: CoreClient für Kontenplan und Journal-Entries.
   * `vibecore.auth`: AuthClient für Login-URL, PKCE-Code-Exchange und Session-Validierung (`/auth/me`).
   * `vibecore.storage`: StorageClient für Direct Uploads, Presigned URLs, Metadaten und Löschungen.
   * `vibecore.payments.pagopar`: PagoparClient für Bestellungen, Polling-Sync und Statusabfragen.
   * `vibecore.payments.stripe`: StripeClient für Checkout Sessions, PaymentIntents und Polling-Sync.
   * `vibecore.client.VibeCoreClient`: Unified Entrypoint mit Context Manager und Lazy Loading.
2. Alle Datenmodelle basieren auf Pydantic v2 mit strikter Validierung.
3. Einheitliche Fehlerhierarchie mit `VibeCoreError` als Basis und typspezifischen Subklassen (`AuthenticationError`, `StorageError`, `PaymentError`, `NetworkError`, `TimeoutError`).
4. HTTP-Transport basiert auf `httpx` mit Timeouts, Retry-Handling und Context Manager Support.

## Consequences

* Entwickler und AI-Agenten interagieren über konsistente, stark typisierte Methoden mit allen Microservices.
* Netzwerkfehler und Timeout-Situationen werden standardisiert abgefangen.
* Saubere Entkopplung zwischen Backend-Services und aufrufenden ERP-Modulen.
