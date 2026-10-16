"""
Tests for Refresh Tokens, JWKS publication, OIDC discovery, and stateless token validation.
"""

from app.models import UserInfo
from app.session import session_manager


def test_issue_token_pair_claims(test_settings):
    user_info = UserInfo(
        user_id="google_test_999",
        email="developer@vibecore.org",
        tenant_id="tenant_vibecore",
        name="Dev User",
        roles=["USER"],
    )

    token_pair = session_manager.issue_token_pair(user_info)
    assert token_pair.access_token is not None
    assert token_pair.refresh_token is not None
    assert token_pair.tenant_id == "tenant_vibecore"
    assert token_pair.expires_in == test_settings.jwt_expiration_minutes * 60
    assert token_pair.refresh_expires_in == test_settings.jwt_refresh_expiration_days * 86400

    # Verify access token claims
    verified_user = session_manager.verify_session_token(token_pair.access_token)
    assert verified_user.user_id == "google_test_999"
    assert verified_user.email == "developer@vibecore.org"
    assert verified_user.tenant_id == "tenant_vibecore"
    assert verified_user.roles == ["USER"]


def test_refresh_token_endpoint_via_body(client):
    user_info = UserInfo(
        user_id="google_test_888",
        email="pascal@vibecore.org",
        tenant_id="tenant_vibecore",
        name="Pascal",
        roles=["ADMIN", "ACCOUNTANT"],
    )
    token_pair = session_manager.issue_token_pair(user_info)

    # Call /auth/token/refresh with refresh token in body
    res = client.post(
        "/auth/token/refresh",
        json={"refresh_token": token_pair.refresh_token},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["tenant_id"] == "tenant_vibecore"
    assert data["user"]["user_id"] == "google_test_888"


def test_refresh_token_endpoint_via_cookie(client):
    user_info = UserInfo(
        user_id="google_test_777",
        email="user777@vibecore.org",
        tenant_id="tenant_vibecore",
        name="User 777",
        roles=["USER"],
    )
    token_pair = session_manager.issue_token_pair(user_info)

    # Call with cookie
    res = client.post(
        "/auth/token/refresh",
        cookies={"vibecore_refresh_token": token_pair.refresh_token},
    )
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_refresh_token_rejects_missing_or_invalid(client):
    # Missing token
    res1 = client.post("/auth/token/refresh", json={})
    assert res1.status_code == 400
    assert "required" in res1.json()["message"].lower()

    # Tampered token
    res2 = client.post("/auth/token/refresh", json={"refresh_token": "tampered.jwt.token"})
    assert res2.status_code in [400, 401]

    # Using access token instead of refresh token
    user_info = UserInfo(
        user_id="google_u", email="u@vibecore.org", tenant_id="tenant_vibecore", roles=["USER"]
    )
    tokens = session_manager.issue_token_pair(user_info)
    res3 = client.post("/auth/token/refresh", json={"refresh_token": tokens.access_token})
    assert res3.status_code == 400
    assert "not a refresh token" in res3.json()["message"].lower()


def test_token_verify_endpoint(client):
    user_info = UserInfo(
        user_id="google_verifier",
        email="verifier@vibecore.org",
        tenant_id="tenant_vibecore",
        name="Verifier User",
        roles=["USER"],
    )
    tokens = session_manager.issue_token_pair(user_info)

    # Verify via header
    res1 = client.post(
        "/auth/verify",
        headers={"Authorization": f"Bearer {tokens.access_token}"},
    )
    assert res1.status_code == 200
    assert res1.json()["user_id"] == "google_verifier"
    assert res1.json()["tenant_id"] == "tenant_vibecore"

    # Verify via query param
    res2 = client.post(f"/auth/verify?token={tokens.access_token}")
    assert res2.status_code == 200

    # Missing token
    res3 = client.post("/auth/verify")
    assert res3.status_code == 401


def test_jwks_and_oidc_endpoints(client):
    # Root JWKS
    res_root_jwks = client.get("/.well-known/jwks.json")
    assert res_root_jwks.status_code == 200
    keys = res_root_jwks.json()["keys"]
    assert len(keys) >= 1
    assert keys[0]["alg"] == "RS256"
    assert keys[0]["kty"] == "RSA"

    # Auth subpath JWKS
    res_auth_jwks = client.get("/auth/.well-known/jwks.json")
    assert res_auth_jwks.status_code == 200
    assert res_auth_jwks.json()["keys"] == keys

    # OIDC Configuration
    res_oidc = client.get("/.well-known/openid-configuration")
    assert res_oidc.status_code == 200
    oidc = res_oidc.json()
    assert oidc["issuer"] == "vibecore-auth"
    assert "/auth/google/login" in oidc["authorization_endpoint"]
    assert "/.well-known/jwks.json" in oidc["jwks_uri"]


def test_session_manager_edge_cases():
    import pytest
    from app.session import SessionException

    # Empty token in verify_session_token
    with pytest.raises(SessionException, match="missing"):
        session_manager.verify_session_token("")

    # Empty token in refresh_session
    with pytest.raises(SessionException, match="missing"):
        session_manager.refresh_session("")

    # Refresh with tenant hint
    user_info = UserInfo(
        user_id="google_hinter",
        email="hinter@vibecore.org",
        tenant_id="tenant_vibecore",
        roles=["USER"],
    )
    tokens = session_manager.issue_token_pair(user_info)
    refreshed = session_manager.refresh_session(tokens.refresh_token, tenant_hint="custom_branch")
    assert refreshed.tenant_id == "tenant_custom_branch"

