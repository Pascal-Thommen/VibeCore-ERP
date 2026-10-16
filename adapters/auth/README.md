# VibeCore ERP: Google OAuth 2.0 & OIDC IdP Microservice

Eigenständiger, wiederverwendbarer Identity Provider (IdP) und Single Sign-On (SSO) Microservice für VibeCore ERP und das gesamte VibeCore-Ökosystem (inklusive AIBill) auf Basis von FastAPI, Google OAuth 2.0 und OpenID Connect (OIDC).

## Architektur & Standards

* **Unabhängiger Identity Provider (IdP)**: Versorgt VibeCore ERP, AIBill und weitere Module dezentral mit verifizierten Identitäten.
* **Isolierter Adapter**: Befolgt strikt die VibeCore Adapter-Isolation (kein direkter Zugriff auf PostgreSQL).
* **RFC 7636 PKCE**: Authorization Code Flow mit Proof Key for Code Exchange (S256).
* **CSRF-Schutz**: Kryptografisch signierter State-Parameter mit HMAC-SHA256 und Zeitstempel.
* **Google Token Exchange & Validierung**: Server-seitiger Token-Austausch über offizielle Google API-Endpunkte und strikte RS256-Signaturprüfung der Google ID-Tokens über Google Public JWKS (`https://www.googleapis.com/oauth2/v3/certs`).
* **Asymmetrisches Token-Management (RS256 / EdDSA)**:
  - Generierung und Signierung von Access- und Refresh-Tokens mit asymmetrischen Schlüsselpaaren (RS256 / EdDSA).
  - Standardisierte Claims: `sub`, `email`, `tenant_id`, `roles`, `exp`, `iat`, `iss`, `aud`, `jti`, `token_use`.
  - Öffentliche JWKS-Endpunkte (`/.well-known/jwks.json`, `/auth/.well-known/jwks.json`) für schlüsselbasierte, dezentrale Token-Validierung ohne Datenbank-Abhängigkeit der konsumierenden Services.
  - OIDC Discovery (`/.well-known/openid-configuration`).
* **Mandanten-Zuordnung (Tenant Resolution)**:
  - Zuweisung von Benutzern zu Mandanten (`tenant_id`) über E-Mail-Domänen-Mapping, hinterlegte Organisationszuordnungen oder persönliche Workspaces.
* **Resilienz & Observability (Säulen 1 & 4)**:
  - Konfigurierbare Timeouts und Retry-Mechanismen mit Exponential Backoff gegen externe Google Endpunkte.
  - Healthchecks: `/healthz` (Kubernetes-Standard) und `/readyz`.
  - Prometheus-Metriken: `/metrics` im standardisierten Plain-Text-Format für Monitoring und Telemetrie.
  - Strukturierte JSON-Audit-Logs mit Trace IDs (`X-Trace-Id`).

## Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/.well-known/jwks.json` | Public JWKS Endpunkt zur dezentralen RS256 Token-Validierung |
| `GET` | `/.well-known/openid-configuration` | OpenID Connect Discovery Dokument |
| `GET` | `/healthz` | Kubernetes Liveness- und Healthcheck-Status |
| `GET` | `/readyz` | Readiness-Check aller Geheimnisse und kryptografischen Schlüssel |
| `GET` | `/metrics` | Prometheus Metriken (Request Counts, Token Issuance, Latency) |
| `GET` | `/auth/.well-known/jwks.json` | JWKS Endpunkt unter dem Auth-Präfix |
| `GET` | `/auth/google/login` | Login initialisieren (PKCE + State), 307 Weiterleitung zu Google |
| `GET` | `/auth/google/callback` | Code Exchange, Google ID-Token Prüfung, Tenant-Auflösung, Token-Paar-Ausstellung |
| `POST` | `/auth/token/refresh` | Ausstellung neuer Access-Tokens via signiertem Refresh-Token |
| `GET` | `/auth/me` | Abruf des verifizierten Benutzerprofils, Mandanten und Rollen |
| `POST` | `/auth/verify` | Zustandsloses Verifizieren von Access-Tokens |
| `POST` | `/auth/logout` | Beenden der Session und Löschen der Cookies |

## Konfiguration

Konfiguration erfolgt über Umgebungsvariablen oder `.env`:

```bash
# Google OAuth 2.0 Credentials
GOOGLE_CLIENT_ID=deine-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=dein-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8001/auth/google/callback

# Asymmetrisches Token-Management (RS256 / EdDSA)
JWT_ALGORITHM=RS256
JWT_KEY_ID=vibecore-auth-key-1
JWT_PRIVATE_KEY_PEM=  # Optional: PEM-String. Falls leer, wird automatisch ein RSA-2048 Keypair erzeugt
JWT_EXPIRATION_MINUTES=60
JWT_REFRESH_EXPIRATION_DAYS=7
JWT_ISSUER=vibecore-auth
JWT_AUDIENCE=vibeshell

# State & Cookie Security
COOKIE_SECRET=mindestens-32-zeichen-cookie-schluessel

# Rollen & Mandanten-Mapping
ADMIN_EMAILS=["pascal@vibecore.org","pascalsolarluchs@gmail.com"]
TENANT_DOMAIN_MAPPING={"vibecore.org": "tenant_vibecore"}
TENANT_ORGANIZATION_MAPPING={"pascal@vibecore.org": "tenant_vibecore"}
DEFAULT_TENANT_ID=tenant_default

# Resilienz & Timeouts
HTTP_TIMEOUT_SECONDS=10.0
HTTP_MAX_RETRIES=3
HTTP_RETRY_DELAY_SECONDS=0.2
HTTP_RETRY_BACKOFF_FACTOR=2.0
```

## Lokale Ausführung & Container

Mit Docker Compose starten:

```bash
docker compose up -d --build
```

Lokal mit Uvicorn starten:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

## Tests ausführen

```bash
pytest tests -v --cov=app
```

## Weiterführende Dokumentation

* [Recherche-Dossier & Technologieentscheidung](RESEARCH_DOSSIER.md)
* [Adapter-Schema Vertrag](.ai/adapter_schema.md)
* [OpenAPI Spezifikation](openapi.json)
