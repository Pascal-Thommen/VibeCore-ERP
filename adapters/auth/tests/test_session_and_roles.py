"""
Tests for VibeCore ERP Session Management & Role Mapping (ADR 0004).
"""

import time

import jwt
import pytest
from app.models import UserInfo
from app.session import SessionException, VibeCoreSessionManager


def test_role_mapping(test_settings):
    manager = VibeCoreSessionManager(app_settings=test_settings)

    # Admin email
    admin_roles = manager.map_roles("pascal@vibecore.org")
    assert "ADMIN" in admin_roles
    assert "ACCOUNTANT" in admin_roles

    # Standard user
    user_roles = manager.map_roles("standard.user@example.com")
    assert user_roles == ["USER"]


def test_session_token_issue_and_verification(test_settings):
    manager = VibeCoreSessionManager(app_settings=test_settings)
    user_info = UserInfo(
        user_id="google_12345",
        email="pascal@vibecore.org",
        name="Pascal Thommen",
        picture="https://example.com/p.jpg",
        roles=["ADMIN", "ACCOUNTANT"],
    )

    token = manager.issue_session_token(user_info)
    assert isinstance(token, str)

    verified_user = manager.verify_session_token(token)
    assert verified_user.user_id == "google_12345"
    assert verified_user.email == "pascal@vibecore.org"
    assert verified_user.name == "Pascal Thommen"
    assert "ADMIN" in verified_user.roles
    assert "ACCOUNTANT" in verified_user.roles


def test_session_token_expired(test_settings):
    manager = VibeCoreSessionManager(app_settings=test_settings)
    now = int(time.time())
    expired_payload = {
        "iss": test_settings.jwt_issuer,
        "aud": test_settings.jwt_audience,
        "sub": "user_123",
        "email": "user@vibecore.org",
        "roles": ["USER"],
        "exp": now - 60,
    }
    expired_token = jwt.encode(expired_payload, key=test_settings.jwt_secret, algorithm="HS256")

    with pytest.raises(SessionException, match="expired"):
        manager.verify_session_token(expired_token)


def test_session_token_invalid_issuer(test_settings):
    manager = VibeCoreSessionManager(app_settings=test_settings)
    now = int(time.time())
    bad_payload = {
        "iss": "rogue-issuer",
        "aud": test_settings.jwt_audience,
        "sub": "user_123",
        "email": "user@vibecore.org",
        "roles": ["USER"],
        "exp": now + 3600,
    }
    bad_token = jwt.encode(bad_payload, key=test_settings.jwt_secret, algorithm="HS256")

    with pytest.raises(SessionException, match="issuer"):
        manager.verify_session_token(bad_token)


def test_session_token_tampered_signature(test_settings):
    manager = VibeCoreSessionManager(app_settings=test_settings)
    now = int(time.time())
    payload = {
        "iss": test_settings.jwt_issuer,
        "aud": test_settings.jwt_audience,
        "sub": "user_123",
        "email": "user@vibecore.org",
        "roles": ["USER"],
        "exp": now + 3600,
    }
    # Signed with wrong secret
    tampered_token = jwt.encode(
        payload, key="wrong-secret-key-12345678901234567890", algorithm="HS256"
    )

    with pytest.raises(SessionException, match="signature"):
        manager.verify_session_token(tampered_token)
