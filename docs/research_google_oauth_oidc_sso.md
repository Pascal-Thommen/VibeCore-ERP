# VibeCore ERP: Google OAuth 2.0 & OIDC SSO Recherche-Dossier

Dieses Dokument verweist auf die vollständige Evaluierung und Spezifikation des Auth-Adapters:
[Vollständiges Recherche-Dossier](../../adapters/auth/RESEARCH_DOSSIER.md)

## Zusammenfassung der Technologieentscheidung

1. **Komponente**: Eigenständiger FastAPI-Microservice als Auth-Adapter (`adapters/auth`).
2. **Architektur-Konformität**:
   * Einhaltung von [ADR 0004](../.ai/adr/0004-authentication-secrets-and-service-trust.md) (JWT Issuer: `vibecore-auth`, Audience: `vibeshell`, Rollen `ADMIN`, `ACCOUNTANT`, `USER`).
   * Einhaltung von [ADR 0008](../.ai/adr/0008-library-and-implementation-policy.md) (Verwendung etablierter Standard-Bibliotheken `PyJWT`, `cryptography`, `httpx`).
   * Strikte Adapter-Isolation: Kein direkter Datenbankzugriff auf Core-Tabellen.
3. **Sicherheitsstandard**:
   * Authorization Code Flow mit PKCE (RFC 7636) mit SHA-256 (`S256`).
   * CSRF-Schutz über kryptografischen State-Parameter mit HMAC-Signatur und Zeitstempel.
   * Server-seitige Validierung des Google ID-Tokens über Google Public JWKS (`https://www.googleapis.com/oauth2/v3/certs`) mit RS256-Signaturprüfung und Claim-Validierung (`iss`, `aud`, `exp`, `email_verified`).
4. **Resilienz & Observability**:
   * Explizite Timeouts für externe Netzwerkaufrufe.
   * Zustandsloser Betrieb für nahtlose Container-Skalierung.
   * Strukturierte Audit-Logs ohne Offenlegung von Geheimnissen.
