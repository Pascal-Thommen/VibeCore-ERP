"""
VibeCore ERP Auth Adapter - Session & Role Manager (ADR 0004).
Issues and validates VibeCore ERP session JWT tokens with strict issuer, audience, and role mapping.
"""

import time
from typing import Any

import jwt

from app.audit import log_audit_event
from app.config import Settings
from app.config import settings as default_settings
from app.models import UserInfo


class SessionException(Exception):
    """Exception raised when session validation fails."""

    def __init__(self, message: str, detail: str | None = None, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.status_code = status_code


class VibeCoreSessionManager:
    def __init__(self, app_settings: Settings | None = None):
        self.settings = app_settings or default_settings

    def map_roles(self, email: str) -> list[str]:
        """
        Maps Google email to VibeCore ERP roles.
        Administrators receive ADMIN and ACCOUNTANT roles.
        Standard users receive the configured default role.
        """
        clean_email = email.strip().lower()
        admins = [a.strip().lower() for a in self.settings.admin_emails]
        if clean_email in admins:
            return ["ADMIN", "ACCOUNTANT"]
        return [self.settings.default_role]

    def create_user_info_from_google(self, google_claims: dict[str, Any]) -> UserInfo:
        """
        Transforms verified Google ID token claims into VibeCore UserInfo.
        """
        sub = google_claims.get("sub", "")
        email = google_claims.get("email", "")
        name = google_claims.get("name")
        picture = google_claims.get("picture")
        roles = self.map_roles(email)

        return UserInfo(
            user_id=f"google_{sub}",
            email=email,
            name=name,
            picture=picture,
            roles=roles,
            auth_provider="google",
            meta={
                "google_sub": sub,
                "email_verified": google_claims.get("email_verified", False),
            },
        )

    def issue_session_token(self, user_info: UserInfo) -> str:
        """
        Creates a VibeCore session JWT token adhering to ADR 0004:
        Issuer: vibecore-auth
        Audience: vibeshell
        Lifetime: 60 minutes
        """
        now = int(time.time())
        exp = now + (self.settings.jwt_expiration_minutes * 60)

        payload = {
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.jwt_audience,
            "sub": user_info.user_id,
            "email": user_info.email,
            "name": user_info.name,
            "picture": user_info.picture,
            "roles": user_info.roles,
            "auth_provider": user_info.auth_provider,
            "iat": now,
            "nbf": now,
            "exp": exp,
            "auth_time": now,
        }

        token = jwt.encode(
            payload,
            key=self.settings.jwt_secret,
            algorithm=self.settings.jwt_algorithm,
        )

        log_audit_event(
            "auth.session.issued",
            "Issued VibeCore session token",
            data={
                "user_id": user_info.user_id,
                "email": user_info.email,
                "roles": user_info.roles,
                "expires_at": exp,
            },
        )
        return token

    def verify_session_token(self, token: str) -> UserInfo:
        """
        Verifies and decodes a VibeCore session JWT token.
        Enforces signature, expiration, issuer, and audience.
        """
        if not token:
            raise SessionException("Session token is missing.")

        try:
            payload = jwt.decode(
                token,
                key=self.settings.jwt_secret,
                algorithms=[self.settings.jwt_algorithm],
                issuer=self.settings.jwt_issuer,
                audience=self.settings.jwt_audience,
                options={
                    "require": ["exp", "iss", "aud", "sub", "email"],
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
                leeway=10,
            )
        except jwt.ExpiredSignatureError as exc:
            raise SessionException(
                "Session token has expired. Please log in again.", detail=str(exc)
            ) from exc
        except jwt.InvalidIssuerError as exc:
            raise SessionException("Invalid token issuer.", detail=str(exc)) from exc
        except jwt.InvalidAudienceError as exc:
            raise SessionException("Invalid token audience.", detail=str(exc)) from exc
        except jwt.PyJWTError as exc:
            raise SessionException("Invalid session token signature.", detail=str(exc)) from exc

        user_info = UserInfo(
            user_id=payload["sub"],
            email=payload["email"],
            name=payload.get("name"),
            picture=payload.get("picture"),
            roles=payload.get("roles", [self.settings.default_role]),
            auth_provider=payload.get("auth_provider", "google"),
            meta={"iat": payload.get("iat"), "exp": payload.get("exp")},
        )

        return user_info


session_manager = VibeCoreSessionManager()
