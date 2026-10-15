"""
VibeCore ERP Auth Adapter - Google OAuth 2.0 & OIDC Client (Zero-Mock Resilient Engine).
Implements token exchange, JWKS caching, RS256 signature verification, and claims validation.
"""

import time
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

from app.audit import log_audit_event
from app.config import Settings
from app.config import settings as default_settings


class GoogleAuthException(Exception):
    """Base exception for Google OAuth/OIDC failures."""

    def __init__(self, message: str, detail: str | None = None, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.status_code = status_code


class GoogleAuthTimeoutException(GoogleAuthException):
    """Raised when external Google API times out (Säule 1)."""

    def __init__(self, message: str = "Google OAuth service timeout"):
        super().__init__(
            message=message,
            detail="Timeout while communicating with Google OAuth APIs",
            status_code=504,
        )


class GoogleOAuthClient:
    def __init__(
        self, app_settings: Settings | None = None, http_client: httpx.AsyncClient | None = None
    ):
        self.settings = app_settings or default_settings
        self._http_client = http_client
        self._jwks_cache: dict[str, Any] | None = None
        self._jwks_cached_at: float = 0.0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client and not self._http_client.is_closed:
            return self._http_client
        timeout = httpx.Timeout(
            connect=5.0,
            read=self.settings.http_timeout_seconds,
            write=5.0,
            pool=5.0,
        )
        return httpx.AsyncClient(timeout=timeout)

    def get_authorization_url(self, state: str, code_challenge: str) -> str:
        """
        Constructs the Google OAuth 2.0 Authorization URL with PKCE (S256).
        """
        params = {
            "client_id": self.settings.google_client_id,
            "redirect_uri": self.settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "online",
            "prompt": "select_account",
        }
        query_string = "&".join(
            f"{k}={httpx.URL('', params={k: v}).query.decode('ascii')}" for k, v in params.items()
        )
        return f"{self.settings.google_auth_url}?{query_string}"

    async def exchange_code_for_tokens(self, code: str, code_verifier: str) -> dict[str, Any]:
        """
        Exchanges authorization code for access_token and id_token using PKCE verifier.
        """
        payload = {
            "code": code,
            "client_id": self.settings.google_client_id,
            "client_secret": self.settings.google_client_secret,
            "redirect_uri": self.settings.google_redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        }

        client = await self._get_client()
        owns_client = client != self._http_client

        try:
            log_audit_event(
                "auth.google.exchange_started", "Initiating token exchange with Google OAuth"
            )
            response = await client.post(
                self.settings.google_token_url,
                data=payload,
                headers={"Accept": "application/json"},
            )
            if response.status_code != 200:
                err_data = (
                    response.json()
                    if response.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
                err_msg = (
                    err_data.get("error_description") or err_data.get("error") or response.text
                )
                log_audit_event(
                    "auth.google.exchange_failed",
                    f"Token exchange failed with HTTP {response.status_code}",
                    data={"status_code": response.status_code, "error": str(err_msg)},
                )
                raise GoogleAuthException(
                    message=f"Google token exchange failed: {err_msg}",
                    detail=f"Google returned HTTP {response.status_code}",
                    status_code=400 if response.status_code < 500 else 502,
                )

            token_data = response.json()
            log_audit_event(
                "auth.google.exchange_success", "Successfully exchanged code for Google tokens"
            )
            return token_data

        except httpx.TimeoutException as exc:
            log_audit_event("auth.google.timeout", "Google token exchange timed out", exc_info=exc)
            raise GoogleAuthTimeoutException("Timeout contacting Google token endpoint") from exc
        except httpx.RequestError as exc:
            log_audit_event(
                "auth.google.network_error",
                f"Network error during token exchange: {exc}",
                exc_info=exc,
            )
            raise GoogleAuthException(
                message="Network error while contacting Google OAuth servers",
                detail=str(exc),
                status_code=502,
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

    async def get_google_jwks(self, force_refresh: bool = False) -> dict[str, Any]:
        """
        Retrieves and caches Google Public JWKS keys for RS256 token verification.
        """
        now = time.time()
        if (
            not force_refresh
            and self._jwks_cache is not None
            and (now - self._jwks_cached_at) < self.settings.jwks_cache_ttl_seconds
        ):
            return self._jwks_cache

        client = await self._get_client()
        owns_client = client != self._http_client

        try:
            log_audit_event("auth.google.jwks_fetch", "Fetching Google Public JWKS certs")
            response = await client.get(self.settings.google_jwks_url)
            if response.status_code != 200:
                raise GoogleAuthException(
                    message="Failed to fetch Google Public JWKS certificates",
                    detail=f"HTTP {response.status_code}",
                    status_code=502,
                )
            jwks = response.json()
            self._jwks_cache = jwks
            self._jwks_cached_at = now
            return jwks
        except httpx.TimeoutException as exc:
            raise GoogleAuthTimeoutException("Timeout fetching Google Public JWKS certs") from exc
        except httpx.RequestError as exc:
            raise GoogleAuthException(
                message="Network error while fetching Google JWKS certificates",
                detail=str(exc),
                status_code=502,
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

    async def validate_id_token(self, id_token: str) -> dict[str, Any]:
        """
        Validates Google ID Token signature against Google Public JWKS and verifies claims.
        """
        if not id_token or not isinstance(id_token, str):
            raise GoogleAuthException("Missing or invalid Google ID Token.")

        try:
            unverified_header = jwt.get_unverified_header(id_token)
        except Exception as exc:
            raise GoogleAuthException("Malformed Google ID Token header.", detail=str(exc)) from exc

        alg = unverified_header.get("alg")
        if alg != "RS256":
            raise GoogleAuthException(
                f"Unsupported algorithm '{alg}' in ID Token header. Expected RS256."
            )

        kid = unverified_header.get("kid")
        if not kid:
            raise GoogleAuthException("Missing key ID (kid) in Google ID Token header.")

        jwks = await self.get_google_jwks(force_refresh=False)
        key_data = self._find_key_in_jwks(jwks, kid)

        if not key_data:
            # Key might have rotated recently; try force refreshing JWKS once
            jwks = await self.get_google_jwks(force_refresh=True)
            key_data = self._find_key_in_jwks(jwks, kid)

        if not key_data:
            raise GoogleAuthException(
                f"Signing key with kid '{kid}' not found in Google JWKS certificates.",
                status_code=401,
            )

        try:
            public_key = RSAAlgorithm.from_jwk(key_data)
        except Exception as exc:
            raise GoogleAuthException(
                "Failed to construct RSA public key from JWKS.", detail=str(exc)
            ) from exc

        try:
            claims = jwt.decode(
                id_token,
                key=public_key,
                algorithms=["RS256"],
                audience=self.settings.google_client_id,
                issuer=self.settings.google_issuer_urls,
                options={
                    "require": ["exp", "iss", "aud", "sub", "email"],
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
                leeway=10,  # 10s leeway for minor clock skew
            )
        except jwt.ExpiredSignatureError as exc:
            raise GoogleAuthException(
                "Google ID Token has expired.", detail=str(exc), status_code=401
            ) from exc
        except jwt.InvalidAudienceError as exc:
            raise GoogleAuthException(
                "Google ID Token audience mismatch.", detail=str(exc), status_code=401
            ) from exc
        except jwt.InvalidIssuerError as exc:
            raise GoogleAuthException(
                "Google ID Token issuer mismatch.", detail=str(exc), status_code=401
            ) from exc
        except jwt.PyJWTError as exc:
            raise GoogleAuthException(
                "Google ID Token signature verification failed.", detail=str(exc), status_code=401
            ) from exc

        # Strict check on email_verified
        if not claims.get("email_verified", False):
            raise GoogleAuthException(
                "Google account email is not verified. VibeCore requires verified email addresses.",
                status_code=403,
            )

        log_audit_event(
            "auth.google.id_token_verified",
            "Successfully validated Google ID Token",
            data={"sub": claims.get("sub"), "email": claims.get("email")},
        )
        return claims

    def _find_key_in_jwks(self, jwks: dict[str, Any], kid: str) -> dict[str, Any] | None:
        keys: list[dict[str, Any]] = jwks.get("keys", [])
        for k in keys:
            if k.get("kid") == kid:
                return k
        return None
