# Recherche-Dossier: Google OAuth 2.0 & OIDC SSO Microservice für VibeCore ERP

## 1. Executive Summary & Problemstellung

Im modernen ERP-Betrieb (insbesondere für paraguayische KMU und dezentrale Unternehmensstrukturen) stellt die Verwaltung separater lokaler Benutzerkonten und Passwörter ein erhebliches Sicherheits- und Effizienzrisiko dar. Password-Fatigue, unsichere Passwörter und manueller Onboarding-Aufwand belasten die Administration.

Ziel dieser Initiative ist die Bereitstellung eines eigenständigen, wiederverwendbaren Single Sign-On (SSO) Microservices auf Basis von Google OAuth 2.0 und OpenID Connect (OIDC). Der Microservice fungiert als isolierter Adapter gemäß VibeCore-Architektur (ADR 0004), kapselt sämtliche Google-spezifischen Protokolle und stellt nach erfolgreicher Authentifizierung standardisierte, signierte VibeCore-Session-Tokens für das Shell-Frontend bereit.

## 2. Evaluierung bewährter Open-Source-Frameworks und Bibliotheken

### 2.1 Python-Bibliotheken

1. **Authlib**
   * *Vorteile*: De-facto Standard für OAuth 1.0, 2.0 und OpenID Connect in Python. Exzellente Unterstützung für PKCE, JWT, JWK und asynchrone HTTP-Clients (httpx). Lizenz: BSD-3-Clause (vollständig kommerziell nutzbar).
   * *Nachteile*: Die Bibliothek deckt sehr viele Szenarien ab (OAuth-Server, OIDC-Provider, verschiedene Web-Frameworks), was die Codebasis relativ groß macht. Für einen reinen OIDC-Client-Adapter wird nur ein Bruchteil benötigt.
   * *Bewertung*: Sehr solide, jedoch mit leichtem Overhead für reine Client-Callbacks.

2. **FastAPI-Users**
   * *Vorteile*: Bietet vorgefertigte Routen für Registrierung, Passwort-Reset und OAuth-Integration.
   * *Nachteile*: Setzt eine direkte Kopplung an Datenbankmodelle (SQLAlchemy ORM, Tortoise, etc.) und eigene Nutzertabellen voraus.
   * *Architektur-Konflikt*: Widerspricht der strikten VibeCore-Doktrin der Adapter-Isolation: Adapter besitzen keinen direkten Datenbankzugriff auf Core-Tabellen. Ein Auth-Adapter soll zustandslos oder minimal gekoppelt agieren und Session-Tokens für die VibeShell emittieren.
   * *Bewertung*: Ungeeignet für die VibeCore-Adapter-Architektur.

3. **Google Auth Library (google-auth, google-auth-oauthlib)**
   * *Vorteile*: Offizielle Google-Bibliothek, vollständige Abdeckung von Google-Spezifika und Service-Accounts.
   * *Nachteile*: Primär für synchrone Workflows und Google Cloud Backend-Dienste optimiert. Asynchrone FastAPI-Workflows mit PKCE erfordern umständliche Wrapper. Zudem zieht sie viele Google-Cloud-Abhängigkeiten mit sich.
   * *Bewertung*: Gut für Google Cloud Server-to-Server, aber unnötig schwerfällig für Web-SSO.

4. **Direkte Kombination aus PyJWT, Cryptography und HTTPX (Empfohlene Kerntechnologie)**
   * *Vorteile*: Maximal schlank, kompromisslos transparent und hochperformant. Verwendet etablierte Standard-Bibliotheken (RFC-konforme Kryptografie und JWT-Engine). Volle asynchrone Unterstützung ohne Blockieren des Event-Loops. Volle Kontrolle über Timeouts, JWKS-Caching und strukturierte Fehlerbehandlung gemäß der Zero-Mock-Doktrin und den vier Säulen von software-testing-audit.
   * *Konformität mit ADR 0008*: Es wird keine eigene Kryptografie erfunden, sondern `cryptography` und `PyJWT` für alle Signatur- und Hash-Prüfungen eingesetzt.
   * *Bewertung*: Beste Lösung für den VibeCore Auth-Adapter.

### 2.2 OIDC-Proxy-Container und Identity-Provider (IdP)

1. **oauth2-proxy**
   * *Vorteile*: Schlanker Go-basierter Reverse-Proxy, bewährt im Kubernetes- und Docker-Umfeld vor Ingress-Controllern.
   * *Nachteile*: Fungiert als vorgeschalteter Proxy, kennt jedoch keine VibeCore-Geschäftslogik, kein paraguayisches ERP-Rollenmodell (ADMIN, ACCOUNTANT, SYSTEM_AGENT gemäß ADR 0004) und keine Core-spezifische Benutzer-Synchronisation.
   * *Bewertung*: Als Infrastruktur-Filter denkbar, ersetzt jedoch nicht den Anwendungs-Auth-Adapter für VibeCore.

2. **Keycloak / Authentik**
   * *Vorteile*: Vollständige Enterprise-Identitätsverwaltung, Multi-Mandanten-Fähigkeit, GUI für Benutzerverwaltung.
   * *Nachteile*: Extrem hoher Ressourcenverbrauch (Java-Laufzeit oder komplexe Python/Postgres-Stacks, oft 1 bis 2 GB RAM).
   * *Architektur-Konflikt*: Widerspricht ADR 0001 und ADR 0004 ("without introducing enterprise infrastructure that a local customer deployment cannot operate reliably"). Ein typischer VibeCore-Kunde in Paraguay betreibt schlanke On-Premise- oder Budget-Cloud-Server.
   * *Bewertung*: Für das VibeCore KMU-Profil überdimensioniert und betrieblich zu wartungsintensiv.

3. **Authelia**
   * *Vorteile*: Schlanker als Keycloak, Fokus auf 2-Faktor-Authentifizierung und Forward-Auth.
   * *Nachteile*: Fokus liegt auf Schutz von statischen Webseiten und Basisservices, geringe Flexibilität für anwendungsspezifische ERP-JWT-Generierung.

## 3. Detaillierte Spezifikation des Auth-Flows (Authorization Code Flow mit PKCE)

Zur Erzielung maximaler Sicherheit nach aktuellem IETF OAuth 2.0 Security Best Current Practice (BCP) wird der **Authorization Code Flow mit PKCE (RFC 7636)** eingesetzt. PKCE verhindert Authorization Code Injection Angriffe selbst dann, wenn der Autorisierungscode abgefangen werden sollte.

### 3.1 Flow-Ablauf

```
+----------+          +---------------+          +-------------------+          +--------------+
| VibeShell|          | Auth-Adapter  |          | Google Accounts   |          | Google JWKS  |
| Browser  |          | (FastAPI)     |          | (OAuth / OIDC)    |          | Certs Endpoint|
+----+-----+          +-------+-------+          +---------+---------+          +-------+------+
     |                        |                            |                            |
 1.  | GET /auth/google/login  |                            |                            |
     +----------------------->+                            |                            |
     |                        | Generiere PKCE (verifier,   |                            |
     |                        | challenge S256) & State.    |                            |
     |                        | Setze HMAC-Cookie (State)   |                            |
 2.  | 307 Redirect Google    |                            |                            |
     |<-----------------------+                            |                            |
 3.  | Redirect zu Google Auth-URL mit PKCE Challenge      |                            |
     +---------------------------------------------------->+                            |
 4.  | Nutzer wählt Account und stimmt Scopes zu           |                            |
     | (openid, email, profile)                            |                            |
 5.  | 302 Redirect zu Callback URI mit Auth-Code & State   |                            |
     |<----------------------------------------------------+                            |
 6.  | GET /auth/google/callback?code=...&state=...        |                            |
     +----------------------->+                            |                            |
     |                        | 1. Validiere State (CSRF)   |                            |
     |                        | 2. Extrahiere Verifier     |                            |
     |                        | 3. POST Token Exchange     |                            |
     |                        +--------------------------->+                            |
     |                        |                            |                            |
     |                        | 4. Return ID- & Access-Tok |                            |
     |                        |<---------------------------+                            |
     |                        |                                                         |
     |                        | 5. Hole Google Public Keys                              |
     |                        +-------------------------------------------------------->+
     |                        | 6. Return JWKS (mit Cache)                              |
     |                        |<--------------------------------------------------------+
     |                        | 7. Validiere RS256 Signatur, aud, iss, exp, email_verified
     |                        | 8. Mappe Profil auf VibeCore Rollen (ADR 0004)          |
     |                        | 9. Erzeuge VibeCore Session-JWT                         |
 7.  | JSON Response / Cookie |                            |                            |
     | mit VibeCore JWT-Token |                            |                            |
     |<-----------------------+                            |                            |
```

### 3.2 Kryptografische Parameter & PKCE

* **Code Verifier**: 64 kryptografisch zufällige Bytes (`secrets.token_urlsafe(64)`), min. 43, max. 128 Zeichen.
* **Code Challenge**: `Base64URL(SHA256(code_verifier))` ohne Padding.
* **Challenge Method**: `S256` (strikt, kein unsicheres `plain`).
* **State**: Kryptografisch zufälliger 32-Byte Token, mit HMAC-SHA256 signiert und an einen Timestamp gebunden (Gültigkeit 10 Minuten).
* **Stateless Resilience**: Der State und der verschlüsselte/signierte Verifier werden in einem HttpOnly, SameSite=Lax Cookie gehalten. Dadurch bleibt der Service absolut zustandslos, skalierbar und resistent gegen Container-Neustarts.

### 3.3 Google Cloud Konfiguration & Scopes

* **Scopes**: `openid`, `email`, `profile`.
* **Redirect URI**: Konfigurierbar über `GOOGLE_REDIRECT_URI` (z. B. `http://localhost:8001/auth/google/callback`).
* **Prompt**: `select_account` zur Vermeidung unklarer automatischer Multi-Account-Konflikte.

### 3.4 Validierung des Google ID-Tokens

1. **Header-Analyse**: Auslesen des Algorithmus (`alg: RS256`) und des Key-Identifikators (`kid`).
2. **JWKS-Abruf & Caching**:
   * Google JWKS Endpunkt: `https://www.googleapis.com/oauth2/v3/certs`.
   * Caching: 1 Stunde im Speicher. Bei Eintreffen eines unbekannten `kid` erfolgt ein einmaliges Force-Refresh (Key-Rotation Handling).
   * Timeout: 5 Sekunden für Netzwerkaufrufe.
3. **Signaturprüfung**: Mathematische Verifikation über den passenden RSA Public Key aus dem JWKS via `PyJWT` und `cryptography`.
4. **Claim-Prüfungen**:
   * `iss` (Issuer) in `["https://accounts.google.com", "accounts.google.com"]`.
   * `aud` (Audience) muss exakt mit `GOOGLE_CLIENT_ID` übereinstimmen.
   * `exp` (Expiration) muss in der Zukunft liegen (mit maximal 10 Sekunden Clock-Skew).
   * `email_verified` muss explizit `true` sein. Unverifizierte E-Mail-Adressen werden strikt abgewiesen.

## 4. VibeCore Rollenmodell & Session-Management (ADR 0004)

Gemäß [ADR 0004](file:///home/pasc/multica_workspaces/kleinkram-a2555fcb8eb5/srv-84-0f78155fdcc6/workdir/VibeCore-ERP/.ai/adr/0004-authentication-secrets-and-service-trust.md):
* **Issuer**: `vibecore-auth`
* **Audience**: `vibeshell`
* **Gültigkeitsdauer**: 60 Minuten (1 Stunde) für Access-Tokens.
* **Initiales Rollenspektrum**:
  * `ADMIN`: Vollzugriff auf Konfiguration, Benutzer und Buchungen.
  * `ACCOUNTANT`: Buchungsberechtigt, Freigabe von Belegen.
  * `SYSTEM_AGENT`: Automatisierte Hintergrunddienste.
  * `USER`: Standard-Lesezugriff.
* **Mapping**: Konfigurierbare Zuweisung von Google E-Mail-Adressen oder Unternehmensdomains zu VibeCore-Rollen via Umgebungsvariablen (`AUTH_ADMIN_EMAILS`, `AUTH_DEFAULT_ROLE`).

## 5. Technologieentscheidung

Für den VibeCore Google OAuth 2.0 / OIDC SSO Microservice wird folgende Architektur festgelegt:
1. **Framework**: FastAPI (asynchron, schlank, native OpenAPI-Generierung).
2. **Kryptografie & Tokens**: `PyJWT` und `cryptography` für RFC-konforme Signaturprüfungen und PKCE.
3. **HTTP-Client**: `httpx.AsyncClient` mit verbindlichen Timeouts (Säule 1: Resilienz).
4. **Zustandslosigkeit**: HMAC-signierte HttpOnly-Cookies für PKCE State, wodurch kein Redis oder flüchtiger Speicher erforderlich ist.
5. **Observability**: Strukturierte Audit-Logs mit Trace IDs, Maskierung sensibler Daten und standardisierte `/health` und `/ready` Endpunkte (Säule 4: Observability).
