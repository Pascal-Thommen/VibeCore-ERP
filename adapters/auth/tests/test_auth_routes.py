"""
Integration tests for FastAPI Auth Adapter routes (/auth/google/login, /auth/google/callback, /auth/me, /auth/logout).
"""

from unittest.mock import AsyncMock

from app.google_client import GoogleOAuthClient
from app.routers.auth import get_google_client


def test_health_endpoints(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "vibecore-auth-adapter"
    assert "timestamp" in data

    ready_res = client.get("/ready")
    assert ready_res.status_code == 200
    assert ready_res.json()["status"] == "ready"


def test_login_endpoint_redirect(client):
    res = client.get("/auth/google/login", follow_redirects=False)
    assert res.status_code == 307
    location = res.headers["location"]
    assert "accounts.google.com" in location
    assert "code_challenge=" in location
    assert "code_challenge_method=S256" in location
    assert "state=" in location
    assert "vibecore_oauth_state" in res.cookies


def test_login_endpoint_json_negotiation(client):
    res = client.get("/auth/google/login", headers={"Accept": "application/json"})
    assert res.status_code == 200
    data = res.json()
    assert "authorization_url" in data
    assert "state" in data
    assert "vibecore_oauth_state" in res.cookies


def test_callback_and_session_lifecycle(client, rsa_keypair, test_settings, make_google_id_token):
    # 1. Initiate login to obtain real signed state
    login_res = client.get("/auth/google/login", headers={"Accept": "application/json"})
    assert login_res.status_code == 200
    state = login_res.json()["state"]
    cookie_state = login_res.cookies.get("vibecore_oauth_state")

    # 2. Prepare real signed Google ID Token
    id_token = make_google_id_token(
        email="pascal@vibecore.org",
        name="Pascal Thommen",
        email_verified=True,
    )

    # 3. Create mock Google client that returns token exchange
    mock_client = GoogleOAuthClient(app_settings=test_settings)
    mock_client.exchange_code_for_tokens = AsyncMock(
        return_value={
            "access_token": "google-mock-access-token-12345",
            "id_token": id_token,
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    )
    mock_client._jwks_cache = rsa_keypair["jwks"]
    mock_client._jwks_cached_at = 9999999999.0

    # 4. Invoke callback with state and cookie
    client.app.dependency_overrides[get_google_client] = lambda: mock_client

    try:
        callback_res = client.get(
            f"/auth/google/callback?code=valid-auth-code&state={state}",
            cookies={"vibecore_oauth_state": cookie_state},
        )
        assert callback_res.status_code == 200
        token_data = callback_res.json()
        assert "access_token" in token_data
        assert token_data["user"]["email"] == "pascal@vibecore.org"
        assert "ADMIN" in token_data["user"]["roles"]
        assert "ACCOUNTANT" in token_data["user"]["roles"]

        # Ensure state cookie was cleared
        assert "vibecore_oauth_state" not in callback_res.cookies

        # 5. Access /auth/me with Bearer token
        access_token = token_data["access_token"]
        me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["email"] == "pascal@vibecore.org"
        assert me_data["roles"] == ["ADMIN", "ACCOUNTANT"]

        # 6. Access /auth/me with Session cookie
        session_cookie = callback_res.cookies.get("vibecore_session")
        if session_cookie:
            me_cookie_res = client.get("/auth/me", cookies={"vibecore_session": session_cookie})
            assert me_cookie_res.status_code == 200
            assert me_cookie_res.json()["email"] == "pascal@vibecore.org"

        # 7. Logout
        logout_res = client.post("/auth/logout")
        assert logout_res.status_code == 200
        assert logout_res.json()["status"] == "logged_out"

        # 8. Access /auth/me without token -> 401 Unauthorized
        unauth_res = client.get("/auth/me")
        assert unauth_res.status_code == 401

    finally:
        client.app.dependency_overrides.clear()
