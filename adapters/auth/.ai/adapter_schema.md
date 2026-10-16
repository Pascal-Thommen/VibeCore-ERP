# Auth Adapter Contract (Google OAuth 2.0 & OIDC IdP Microservice)

**Status:** IMPLEMENTED (Identity Provider & Single Sign-On Microservice)

Der Auth-Adapter folgt [ADR 0004](../../../.ai/adr/0004-authentication-secrets-and-service-trust.md) und [ADR 0008](../../../.ai/adr/0008-library-and-implementation-policy.md).
Er exponiert `openapi.json`, agiert als isolierter Identity Provider (IdP) und SSO-Microservice für VibeCore ERP und AIBill und greift niemals direkt auf die PostgreSQL-Datenbank des Finance Core zu.

## Adapter identity

* **Name:** vibecore-auth-adapter
* **Version:** 0.1.0
* **Owner:** VibeCore Architecture & Security
* **OpenAPI:** `openapi.json`

## Core contract

* **Inbound endpoints:**
  * `GET /.well-known/jwks.json` (Dezentrale Token-Validierung via Public JWKS Key Set)
  * `GET /.well-known/openid-configuration` (Standardisiertes OIDC Discovery-Dokument)
  * `GET /healthz` & `GET /health` (Kubernetes Liveness Check und Konfigurationsstatus)
  * `GET /readyz` & `GET /ready` (Readiness Check für Secrets und kryptografische Schlüsselpaare)
  * `GET /metrics` (Prometheus Metrics Plain-Text Exposition Format)
  * `GET /auth/.well-known/jwks.json` (Public JWKS unter dem Auth-Pfad)
  * `GET /auth/google/login` (PKCE & State Initialisierung, 307 Redirect zu Google)
  * `GET /auth/google/callback` (Code Exchange, ID-Token Validierung, Mandanten-Zuordnung, RS256 Token-Paar Erstellung)
  * `POST /auth/token/refresh` (Zustandsloses Erneuern von Access-Tokens via signiertem Refresh-Token)
  * `GET /auth/me` (Token-Prüfung, Userinfo, Mandanten- und Rollen-Extraktion)
  * `POST /auth/verify` (Zustandsloses Prüfen von Access-Tokens)
  * `POST /auth/logout` (Löschen von Session-, Refresh- und State-Cookies)
* **Outbound operations:**
  * `POST https://oauth2.googleapis.com/token` (Server-seitiger Token Exchange mit PKCE verifier)
  * `GET https://www.googleapis.com/oauth2/v3/certs` (Abruf des Google Public JWKS zur RS256-Signaturprüfung)
* **Kryptographie & Tokens:**
  * Asymmetrische Token-Signierung via RS256 (2048-bit RSA) oder EdDSA (Ed25519).
  * Standardisierte Claims: `sub`, `email`, `tenant_id`, `roles`, `exp`, `iat`, `iss`, `aud`, `jti`, `token_use`.
  * Public JWKS (RFC 7517) zur dezentralen Verifikation ohne Datenbank-Abhängigkeit konsumierender Services.
* **Mandanten-Zuordnung:**
  * Zuweisung von authentifizierten Benutzern zu Mandanten (`tenant_id`) über E-Mail-Domänen-Mapping, hinterlegte Organisationszuordnungen oder persönliche Workspaces.
* **Resilienz & Observability:**
  * Konfigurierbare Timeouts (10s) und Exponential Backoff Retry (3 Retries) gegen externe Google API Calls.
  * `X-Trace-Id` / `X-Request-Id` in allen HTTP-Headern und strukturierten Audit-Logs.
  * Prometheus-Metriken für Request-Raten, Token-Generierung, Latenzen und Fehler.

## Payload evolution

Alle JSON-Antworten akzeptieren optionale `meta` und `custom_data` Objekte für abwärtskompatible Erweiterungen.

## Security boundary

Dieser Adapter besitzt keinen direkten Zugriff auf PostgreSQL.
Benötigte Umgebungsvariablen / Secrets:
* `GOOGLE_CLIENT_ID`: Öffentliche Client ID aus Google Cloud Console.
* `GOOGLE_CLIENT_SECRET`: Vertrauliches Client Secret für Token Exchange.
* `GOOGLE_REDIRECT_URI`: Autorisierte Callback-URL.
* `JWT_ALGORITHM`: RS256 (Standard) oder EdDSA.
* `JWT_KEY_ID`: Eindeutiger Bezeichner des aktiven Signaturschlüssels im JWKS.
* `JWT_PRIVATE_KEY_PEM`: Optionales PEM für persistenten RSA/Ed25519 Private Key.
* `COOKIE_SECRET`: Geheimer Schlüssel zur HMAC-Signierung von State und PKCE Cookies.
Injektion erfolgt über Docker Secrets oder geschützte Umgebungsvariablen.
