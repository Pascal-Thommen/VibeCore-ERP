"""
Pytest configuration and cryptographic fixtures for VibeCore Auth Adapter tests.
Uses real RSA key generation (cryptography) to test authentic JWKS signing and verification (Zero-Mock-Doktrin).
"""

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from app.config import Settings
from app.main import app


@pytest.fixture(scope="session")
def rsa_keypair():
    """Generates an authentic in-memory RSA keypair for testing JWKS RS256 token verification."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    jwk_dict = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk_dict["kid"] = "test-key-id-2026"
    jwk_dict["use"] = "sig"
    jwk_dict["alg"] = "RS256"

    jwks = {"keys": [jwk_dict]}

    return {
        "private_key": private_key,
        "private_pem": pem_private,
        "public_key": public_key,
        "jwk": jwk_dict,
        "jwks": jwks,
        "kid": "test-key-id-2026",
    }


@pytest.fixture
def test_settings():
    """Provides isolated test settings."""
    return Settings(
        google_client_id="test-client-id-1234.apps.googleusercontent.com",
        google_client_secret="test-client-secret-xyz",
        google_redirect_uri="http://localhost:8001/auth/google/callback",
        jwt_secret="test-jwt-secret-very-long-and-secure-32-chars",
        cookie_secret="test-cookie-secret-very-long-and-secure-32-chars",
        admin_emails=["pascal@vibecore.org", "admin@vibecore.org"],
        default_role="USER",
        http_timeout_seconds=5.0,
    )


@pytest.fixture
def make_google_id_token(rsa_keypair, test_settings):
    """Factory fixture to create signed Google ID Tokens with custom claims."""

    def _generator(
        sub: str = "10987654321",
        email: str = "pascal@vibecore.org",
        name: str = "Pascal Thommen",
        picture: str = "https://example.com/pascal.jpg",
        email_verified: bool = True,
        aud: str | None = None,
        iss: str = "https://accounts.google.com",
        exp_offset: int = 3600,
        kid: str | None = None,
    ) -> str:
        now = int(time.time())
        claims = {
            "iss": iss,
            "aud": aud or test_settings.google_client_id,
            "sub": sub,
            "email": email,
            "email_verified": email_verified,
            "name": name,
            "picture": picture,
            "iat": now,
            "exp": now + exp_offset,
        }
        headers = {"kid": kid or rsa_keypair["kid"], "alg": "RS256"}
        return jwt.encode(
            claims,
            key=rsa_keypair["private_pem"],
            algorithm="RS256",
            headers=headers,
        )

    return _generator


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    with TestClient(app) as test_client:
        yield test_client
