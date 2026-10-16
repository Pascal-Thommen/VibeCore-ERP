"""
Tests for Google ID Token RS256 validation via Public JWKS (Zero-Mock-Doktrin).
"""

import pytest

from app.google_client import GoogleAuthException, GoogleOAuthClient


@pytest.mark.asyncio
async def test_valid_id_token_verification(rsa_keypair, test_settings, make_google_id_token):
    token = make_google_id_token(
        email="pascal@vibecore.org",
        name="Pascal Thommen",
        email_verified=True,
    )

    client = GoogleOAuthClient(app_settings=test_settings)
    # Inject cached JWKS with real public key from test fixture
    client._jwks_cache = rsa_keypair["jwks"]
    client._jwks_cached_at = 9999999999.0

    claims = await client.validate_id_token(token)
    assert claims["email"] == "pascal@vibecore.org"
    assert claims["name"] == "Pascal Thommen"
    assert claims["email_verified"] is True
    assert claims["sub"] == "10987654321"


@pytest.mark.asyncio
async def test_unverified_email_rejected(rsa_keypair, test_settings, make_google_id_token):
    token = make_google_id_token(
        email="unverified@vibecore.org",
        email_verified=False,
    )

    client = GoogleOAuthClient(app_settings=test_settings)
    client._jwks_cache = rsa_keypair["jwks"]
    client._jwks_cached_at = 9999999999.0

    with pytest.raises(GoogleAuthException) as exc_info:
        await client.validate_id_token(token)
    assert exc_info.value.status_code == 403
    assert "email is not verified" in exc_info.value.message


@pytest.mark.asyncio
async def test_audience_mismatch_rejected(rsa_keypair, test_settings, make_google_id_token):
    token = make_google_id_token(
        aud="malicious-client-id.apps.googleusercontent.com",
    )

    client = GoogleOAuthClient(app_settings=test_settings)
    client._jwks_cache = rsa_keypair["jwks"]
    client._jwks_cached_at = 9999999999.0

    with pytest.raises(GoogleAuthException) as exc_info:
        await client.validate_id_token(token)
    assert exc_info.value.status_code == 401
    assert "audience mismatch" in exc_info.value.message


@pytest.mark.asyncio
async def test_issuer_mismatch_rejected(rsa_keypair, test_settings, make_google_id_token):
    token = make_google_id_token(
        iss="https://fake-accounts.example.com",
    )

    client = GoogleOAuthClient(app_settings=test_settings)
    client._jwks_cache = rsa_keypair["jwks"]
    client._jwks_cached_at = 9999999999.0

    with pytest.raises(GoogleAuthException) as exc_info:
        await client.validate_id_token(token)
    assert exc_info.value.status_code == 401
    assert "issuer mismatch" in exc_info.value.message


@pytest.mark.asyncio
async def test_expired_token_rejected(rsa_keypair, test_settings, make_google_id_token):
    token = make_google_id_token(
        exp_offset=-100,  # Expired in past
    )

    client = GoogleOAuthClient(app_settings=test_settings)
    client._jwks_cache = rsa_keypair["jwks"]
    client._jwks_cached_at = 9999999999.0

    with pytest.raises(GoogleAuthException) as exc_info:
        await client.validate_id_token(token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.message


@pytest.mark.asyncio
async def test_missing_or_unknown_kid(rsa_keypair, test_settings, make_google_id_token):
    token = make_google_id_token(
        kid="unknown-non-existent-kid-999",
    )

    client = GoogleOAuthClient(app_settings=test_settings)
    client._jwks_cache = rsa_keypair["jwks"]
    client._jwks_cached_at = 9999999999.0

    # Mock jwks endpoint for force refresh to also not have the unknown kid
    async def fake_get_jwks(force_refresh=False):
        return rsa_keypair["jwks"]

    client.get_google_jwks = fake_get_jwks

    with pytest.raises(GoogleAuthException) as exc_info:
        await client.validate_id_token(token)
    assert exc_info.value.status_code == 401
    assert "not found in Google JWKS" in exc_info.value.message
