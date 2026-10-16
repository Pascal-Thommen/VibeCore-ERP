"""
VibeCore ERP Auth Adapter - Session & Token Manager (ADR 0004 & RS256/EdDSA IdP).
Issues and validates standardized access and refresh JWT tokens:
- Claims: sub, email, tenant_id, roles, exp, iat, iss, aud, jti, token_use
- Cryptographic asymmetric signing via CryptoManager (RS256 / EdDSA)
- Multi-tenant assignment via TenantResolver
"""

import time
from typing import Any
import uuid

from app.audit import log_audit_event
from app.config import Settings
from app.config import settings as default_settings
from app.crypto import CryptoException, crypto_manager
from app.metrics import metrics_registry
from app.models import TokenResponse, UserInfo
from app.tenant import tenant_resolver


class SessionException(Exception):
    """Exception raised when session validation or token operations fail."""

    def __init__(self, message: str, detail: str | None = None, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.status_code = status_code


class VibeCoreSessionManager:
    def __init__(
        self,
        app_settings: Settings | None = None,
        crypto_mgr=None,
        tenant_res=None,
    ):
        self.settings = app_settings or default_settings
        self.crypto = crypto_mgr or crypto_manager
        self.tenant_resolver = tenant_res or tenant_resolver

    def map_roles(self, email: str) -> list[str]:
        """
        Maps user email to VibeCore ERP roles.
        Administrators receive ADMIN and ACCOUNTANT roles.
        Standard users receive the configured default role.
        """
        clean_email = email.strip().lower()
        admins = [a.strip().lower() for a in self.settings.admin_emails]
        if clean_email in admins:
            return ["ADMIN", "ACCOUNTANT"]
        return [self.settings.default_role]

    def create_user_info_from_google(
        self, google_claims: dict[str, Any], org_hint: str | None = None
    ) -> UserInfo:
        """
        Transforms verified Google ID token claims into VibeCore UserInfo,
        including Mandanten-Zuordnung (tenant_id).
        """
        sub = google_claims.get("sub", "")
        email = google_claims.get("email", "")
        name = google_claims.get("name")
        picture = google_claims.get("picture")
        roles = self.map_roles(email)
        tenant_id = self.tenant_resolver.resolve(email=email, org_hint=org_hint)

        metrics_registry.observe_tenant(tenant_id)

        return UserInfo(
            user_id=f"google_{sub}",
            email=email,
            tenant_id=tenant_id,
            name=name,
            picture=picture,
            roles=roles,
            auth_provider="google",
            meta={
                "google_sub": sub,
                "email_verified": google_claims.get("email_verified", False),
            },
        )

    def issue_token_pair(self, user_info: UserInfo) -> TokenResponse:
        """
        Generates and signs both Access Token and Refresh Token adhering to ADR 0004:
        Standardized Claims: sub, email, tenant_id, roles, exp, iat, iss, aud, jti.
        Access token validity: 60 minutes.
        Refresh token validity: 7 days.
        """
        now = int(time.time())
        access_exp = now + (self.settings.jwt_expiration_minutes * 60)
        refresh_exp = now + (self.settings.jwt_refresh_expiration_days * 86400)

        jti_access = f"vcat_{uuid.uuid4().hex}"
        jti_refresh = f"vcrt_{uuid.uuid4().hex}"

        # 1. Access Token Payload
        access_payload = {
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.jwt_audience,
            "sub": user_info.user_id,
            "email": user_info.email,
            "tenant_id": user_info.tenant_id,
            "roles": user_info.roles,
            "name": user_info.name,
            "picture": user_info.picture,
            "auth_provider": user_info.auth_provider,
            "token_use": "access",
            "jti": jti_access,
            "iat": now,
            "nbf": now,
            "exp": access_exp,
            "auth_time": now,
        }

        # 2. Refresh Token Payload
        refresh_payload = {
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.jwt_audience,
            "sub": user_info.user_id,
            "email": user_info.email,
            "tenant_id": user_info.tenant_id,
            "roles": user_info.roles,
            "token_use": "refresh",
            "jti": jti_refresh,
            "iat": now,
            "nbf": now,
            "exp": refresh_exp,
        }

        access_token = self.crypto.sign(access_payload)
        refresh_token = self.crypto.sign(refresh_payload)

        metrics_registry.record_token_issued("access")
        metrics_registry.record_token_issued("refresh")

        log_audit_event(
            "auth.session.issued",
            "Issued VibeCore RS256 token pair",
            data={
                "user_id": user_info.user_id,
                "email": user_info.email,
                "tenant_id": user_info.tenant_id,
                "roles": user_info.roles,
                "access_exp": access_exp,
                "refresh_exp": refresh_exp,
            },
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=self.settings.jwt_expiration_minutes * 60,
            refresh_expires_in=self.settings.jwt_refresh_expiration_days * 86400,
            tenant_id=user_info.tenant_id,
            user=user_info,
            meta={"jti_access": jti_access, "jti_refresh": jti_refresh},
        )

    def issue_session_token(self, user_info: UserInfo) -> str:
        """Backwards compatible access token issuance."""
        token_pair = self.issue_token_pair(user_info)
        return token_pair.access_token

    def verify_session_token(self, token: str) -> UserInfo:
        """
        Verifies and decodes a VibeCore access token using asymmetric public key.
        Enforces signature, expiration, issuer, audience, and token_use == 'access'.
        """
        if not token:
            raise SessionException("Session token is missing.")

        try:
            payload = self.crypto.verify(
                token=token,
                expected_issuer=self.settings.jwt_issuer,
                expected_audience=self.settings.jwt_audience,
                leeway=10,
            )
        except CryptoException as exc:
            raise SessionException(
                message=exc.message, detail=exc.detail, status_code=exc.status_code
            ) from exc

        token_use = payload.get("token_use", "access")
        if token_use != "access":
            raise SessionException(
                "Invalid token type for session verification. Expected access token."
            )

        tenant_id = payload.get("tenant_id") or self.settings.default_tenant_id

        user_info = UserInfo(
            user_id=payload["sub"],
            email=payload.get("email", ""),
            tenant_id=tenant_id,
            name=payload.get("name"),
            picture=payload.get("picture"),
            roles=payload.get("roles", [self.settings.default_role]),
            auth_provider=payload.get("auth_provider", "google"),
            meta={"iat": payload.get("iat"), "exp": payload.get("exp"), "jti": payload.get("jti")},
        )

        return user_info

    def refresh_session(
        self, refresh_token: str, tenant_hint: str | None = None
    ) -> TokenResponse:
        """
        Validates refresh token and issues a new access token and rotated refresh token.
        """
        if not refresh_token:
            raise SessionException("Refresh token is missing.")

        try:
            payload = self.crypto.verify(
                token=refresh_token,
                expected_issuer=self.settings.jwt_issuer,
                expected_audience=self.settings.jwt_audience,
                leeway=10,
            )
        except CryptoException as exc:
            raise SessionException(
                message=f"Invalid refresh token: {exc.message}",
                detail=exc.detail,
                status_code=exc.status_code,
            ) from exc

        token_use = payload.get("token_use")
        if token_use != "refresh":
            raise SessionException(
                "Provided token is not a refresh token.",
                detail=f"Token use was '{token_use}' instead of 'refresh'.",
                status_code=400,
            )

        email = payload.get("email", "")
        sub = payload["sub"]
        roles = payload.get("roles", [self.settings.default_role])

        # Resolve or verify tenant
        tenant_id = payload.get("tenant_id")
        if tenant_hint:
            tenant_id = self.tenant_resolver.resolve(email=email, org_hint=tenant_hint)
        elif not tenant_id:
            tenant_id = self.tenant_resolver.resolve(email=email)

        user_info = UserInfo(
            user_id=sub,
            email=email,
            tenant_id=tenant_id,
            name=payload.get("name"),
            picture=payload.get("picture"),
            roles=roles,
            auth_provider=payload.get("auth_provider", "google"),
            meta={"refreshed_from_jti": payload.get("jti")},
        )

        new_tokens = self.issue_token_pair(user_info)
        metrics_registry.record_token_refreshed()

        log_audit_event(
            "auth.session.refreshed",
            "Successfully refreshed VibeCore token pair",
            data={
                "user_id": user_info.user_id,
                "email": user_info.email,
                "tenant_id": user_info.tenant_id,
            },
        )

        return new_tokens


session_manager = VibeCoreSessionManager()
