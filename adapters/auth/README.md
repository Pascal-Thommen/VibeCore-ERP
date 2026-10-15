# VibeCore ERP: Google OAuth 2.0 & OIDC SSO Adapter

Eigenständiger, wiederverwendbarer Single Sign-On (SSO) Microservice für VibeCore ERP auf Basis von FastAPI, Google OAuth 2.0 und OpenID Connect (OIDC).

## Architektur & Standards

* **Isolierter Adapter**: Befolgt strikt die VibeCore Adapter-Isolation (kein direkter Zugriff auf PostgreSQL).
* **RFC 7636 PKCE**: Authorization Code Flow mit Proof Key for Code Exchange (S256).
* **CSRF-Schutz**: Kryptografisch signierter State-Parameter mit HMAC-SHA256 und Zeitstempel.
* **Token-Validierung**: Vollständige RS256-Signaturprüfung von Google ID-Tokens über Google Public JWKS (`https://www.googleapis.com/oauth2/v3/certs`).
* **VibeCore Sessions**: Erzeugt standardisierte Session-JWTs gemäß ADR 0004 (Issuer: `vibecore-auth`, Audience: `vibeshell`, Lebensdauer: 60 Minuten).
* **Observability**: Strukturierte JSON-Audit-Logs mit Trace IDs (`X-Trace-Id`) und Healthcheck-Endpunkten (`/health`, `/ready`).

## Endpunkte

| Methode | Pfad | Beschreibung |
|---|---|---|
| `GET` | `/health` | Liveness- und Healthcheck-Status |
| `GET` | `/ready` | Readiness-Check aller Geheimnisse |
| `GET` | `/auth/google/login` | Login initialisieren (PKCE + State), 307 Weiterleitung zu Google |
| `GET` | `/auth/google/callback` | Code Exchange, ID-Token Validierung, Ausstellung des VibeCore Session-Tokens |
| `GET` | `/auth/me` | Abruf des verifizierten Benutzerprofils und der VibeCore-Rollen |
| `POST` | `/auth/logout` | Beenden der Session und Löschen der Cookies |

## Konfiguration

Konfiguration erfolgt über Umgebungsvariablen oder `.env`:

```bash
GOOGLE_CLIENT_ID=deine-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=dein-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8001/auth/google/callback
JWT_SECRET=mindestens-32-zeichen-geheimer-schluessel
COOKIE_SECRET=mindestens-32-zeichen-cookie-schluessel
ADMIN_EMAILS=["pascal@vibecore.org","pascalsolarluchs@gmail.com"]
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
pytest tests -v
```

## Weiterführende Dokumentation

* [Recherche-Dossier & Technologieentscheidung](RESEARCH_DOSSIER.md)
* [Adapter-Schema Vertrag](.ai/adapter_schema.md)
* [OpenAPI Spezifikation](openapi.json)
