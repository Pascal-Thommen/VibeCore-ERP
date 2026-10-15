# Auth Adapter Contract (Google OAuth 2.0 & OIDC SSO)

**Status:** IMPLEMENTED (Single Sign-On & OIDC Session Provider)

Der Auth-Adapter folgt [ADR 0004](../../../.ai/adr/0004-authentication-secrets-and-service-trust.md) und [ADR 0008](../../../.ai/adr/0008-library-and-implementation-policy.md).
Er exponiert `openapi.json`, agiert als isolierter SSO-Microservice und greift niemals direkt auf die PostgreSQL-Datenbank des Finance Core zu.

## Adapter identity

* **Name:** vibecore-auth-adapter
* **Version:** 0.1.0
* **Owner:** VibeCore Architecture & Security
* **OpenAPI:** `openapi.json`

## Core contract

* **Inbound endpoints:**
  * `GET /health` (Liveness Check und Konfigurationsstatus)
  * `GET /ready` (Readiness Check für Container Orchestration)
  * `GET /auth/google/login` (PKCE & State Initialisierung, 307 Redirect zu Google)
  * `GET /auth/google/callback` (Code Exchange, Token Validation, VibeCore JWT Erstellung)
  * `GET /auth/me` (Token-Prüfung, Userinfo und Rollen-Extraktion)
  * `POST /auth/logout` (Löschen von Session- und State-Cookies)
* **Outbound operations:**
  * `POST https://oauth2.googleapis.com/token` (Server-seitiger Token Exchange mit PKCE verifier)
  * `GET https://www.googleapis.com/oauth2/v3/certs` (Abruf des Google Public JWKS zur RS256-Signaturprüfung)
* **Authentication:**
  * Client Authentifizierung über Authorization Code Flow mit PKCE (RFC 7636).
  * VibeCore Session Tokens signiert mit JWT Secret (Issuer: `vibecore-auth`, Audience: `vibeshell`).
* **Correlation ID:**
  * `X-Trace-Id` / `X-Request-Id` in allen HTTP-Headern und strukturierten Logs.
* **Retry and recovery:**
  * 10 Sekunden Timeout für externe Google API Calls.
  * Automatisches Caching von Google JWKS mit Cache-Invalidierung bei unbekannten Key IDs (`kid`).

## Payload evolution

Alle JSON-Antworten akzeptieren optionale `meta` und `custom_data` Objekte für abwärtskompatible Erweiterungen.

## Security boundary

Dieser Adapter besitzt keinen direkten Zugriff auf PostgreSQL.
Benötigte Umgebungsvariablen / Secrets:
* `GOOGLE_CLIENT_ID`: Öffentliche Client ID aus Google Cloud Console.
* `GOOGLE_CLIENT_SECRET`: Vertrauliches Client Secret für Token Exchange.
* `GOOGLE_REDIRECT_URI`: Autorisierte Callback-URL.
* `JWT_SECRET`: Geheimer Schlüssel zur Signierung der VibeCore-Session-JWTs.
* `COOKIE_SECRET`: Geheimer Schlüssel zur HMAC-Signierung von State und PKCE Cookies.
Injektion erfolgt über Docker Secrets oder geschützte Umgebungsvariablen.
