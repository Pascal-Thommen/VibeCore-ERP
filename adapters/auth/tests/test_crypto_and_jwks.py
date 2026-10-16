"""
Tests for Asymmetric Cryptographic Key Management (RS256 & EdDSA) and RFC 7517 JWKS.
"""

import json
import os
import tempfile
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from jwt.algorithms import RSAAlgorithm
import pytest

from app.config import Settings
from app.crypto import CryptoException, CryptoManager


def test_rsa_keypair_generation_and_jwks():
    settings = Settings(jwt_algorithm="RS256", jwt_key_id="test-rsa-key-1")
    mgr = CryptoManager(app_settings=settings)

    jwks = mgr.get_jwks()
    assert "keys" in jwks
    assert len(jwks["keys"]) == 1

    key = jwks["keys"][0]
    assert key["kty"] == "RSA"
    assert key["use"] == "sig"
    assert key["alg"] == "RS256"
    assert key["kid"] == "test-rsa-key-1"
    assert "n" in key
    assert "e" in key

    # Verify PEM public key
    pem = mgr.get_public_key_pem()
    assert "-----BEGIN PUBLIC KEY-----" in pem
    assert "-----END PUBLIC KEY-----" in pem


def test_eddsa_keypair_generation_and_jwks():
    settings = Settings(jwt_algorithm="EdDSA", jwt_key_id="test-eddsa-key-1")
    mgr = CryptoManager(app_settings=settings)

    jwks = mgr.get_jwks()
    assert "keys" in jwks
    key = jwks["keys"][0]
    assert key["kty"] == "OKP"
    assert key["use"] == "sig"
    assert key["alg"] == "EdDSA"
    assert key["kid"] == "test-eddsa-key-1"

    payload = {"sub": "user_ed", "exp": int(time.time()) + 3600}
    token = mgr.sign(payload)
    decoded = mgr.verify(token)
    assert decoded["sub"] == "user_ed"


def test_crypto_manager_load_from_pem_string():
    # Generate an RSA private key and serialize to PEM
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_str = rsa_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    settings = Settings(
        jwt_algorithm="RS256",
        jwt_key_id="custom-pem-key",
        jwt_private_key_pem=pem_str,
    )
    mgr = CryptoManager(app_settings=settings)
    assert mgr.key_id == "custom-pem-key"

    token = mgr.sign({"sub": "user_pem", "exp": int(time.time()) + 3600})
    decoded = mgr.verify(token)
    assert decoded["sub"] == "user_pem"


def test_crypto_manager_load_from_pem_file():
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_bytes = rsa_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    with tempfile.NamedTemporaryFile("wb", delete=False) as f:
        f.write(pem_bytes)
        file_path = f.name

    try:
        settings = Settings(
            jwt_algorithm="RS256",
            jwt_key_id="file-pem-key",
            jwt_private_key_path=file_path,
        )
        mgr = CryptoManager(app_settings=settings)
        token = mgr.sign({"sub": "user_file", "exp": int(time.time()) + 3600})
        decoded = mgr.verify(token)
        assert decoded["sub"] == "user_file"
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


def test_crypto_verify_external_jwk_roundtrip():
    settings = Settings(jwt_algorithm="RS256", jwt_key_id="jwk-roundtrip-key")
    mgr = CryptoManager(app_settings=settings)

    payload = {
        "sub": "user_jwk_test",
        "iss": "vibecore-auth",
        "aud": "vibeshell",
        "exp": int(time.time()) + 3600,
    }
    token = mgr.sign(payload)

    # Decode using the exported JWKS key via PyJWT RSAAlgorithm
    jwks = mgr.get_jwks()
    jwk_key = jwks["keys"][0]
    public_key = RSAAlgorithm.from_jwk(jwk_key)

    verified = jwt.decode(
        token,
        key=public_key,
        algorithms=["RS256"],
        issuer="vibecore-auth",
        audience="vibeshell",
    )
    assert verified["sub"] == "user_jwk_test"
    assert verified["iss"] == "vibecore-auth"


def test_crypto_verify_exceptions():
    settings = Settings(jwt_algorithm="RS256", jwt_key_id="key-exc-test")
    mgr = CryptoManager(app_settings=settings)

    # Empty token
    with pytest.raises(CryptoException, match="non-empty string"):
        mgr.verify("")

    # Malformed header
    with pytest.raises(CryptoException, match="Malformed JWT header"):
        mgr.verify("not-a-token")

    # Unsupported algorithm
    hs256_token = jwt.encode({"sub": "u1"}, key="secret", algorithm="HS256")
    with pytest.raises(CryptoException, match="Unsupported token algorithm"):
        mgr.verify(hs256_token)

    # Expired token
    expired_token = mgr.sign({"sub": "u1", "exp": int(time.time()) - 100})
    with pytest.raises(CryptoException, match="expired"):
        mgr.verify(expired_token)

    # Invalid issuer
    wrong_iss_token = mgr.sign(
        {"sub": "u1", "iss": "wrong-iss", "exp": int(time.time()) + 3600}
    )
    with pytest.raises(CryptoException, match="issuer"):
        mgr.verify(wrong_iss_token, expected_issuer="vibecore-auth")

    # Invalid audience
    wrong_aud_token = mgr.sign(
        {"sub": "u1", "aud": "wrong-aud", "exp": int(time.time()) + 3600}
    )
    with pytest.raises(CryptoException, match="audience"):
        mgr.verify(wrong_aud_token, expected_audience="vibeshell")

    # Tampered signature
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tampered = jwt.encode(
        {"sub": "u1", "exp": int(time.time()) + 3600},
        key=other_key,
        algorithm="RS256",
        headers={"kid": "key-exc-test"},
    )
    with pytest.raises(CryptoException, match="cryptographic signature"):
        mgr.verify(tampered)


def test_crypto_custom_headers_and_unknown_kid():
    settings = Settings(jwt_algorithm="RS256", jwt_key_id="known-kid")
    mgr = CryptoManager(app_settings=settings)

    token = mgr.sign({"sub": "u1", "exp": int(time.time()) + 3600}, headers={"custom_header": "val123"})
    hdr = jwt.get_unverified_header(token)
    assert hdr["custom_header"] == "val123"
    assert hdr["kid"] == "known-kid"

    # Token with different kid still decodes if signature matches key
    token_diff_kid = jwt.encode(
        {"sub": "u1", "exp": int(time.time()) + 3600},
        key=mgr._private_key,
        algorithm="RS256",
        headers={"kid": "other-kid"},
    )
    decoded = mgr.verify(token_diff_kid)
    assert decoded["sub"] == "u1"

