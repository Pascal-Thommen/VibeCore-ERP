"""
Tests for PKCE (RFC 7636) and HMAC signed CSRF state validation.
"""

import time

import pytest

from app.pkce import (
    compute_code_challenge,
    create_signed_state,
    generate_code_verifier,
    verify_signed_state,
)


def test_generate_code_verifier_rfc_conformance():
    """Verifier must be between 43 and 128 characters and strictly URL-safe."""
    for _ in range(20):
        verifier = generate_code_verifier()
        assert 43 <= len(verifier) <= 128
        # Ensure only RFC 7636 unreserved characters
        assert all(c.isalnum() or c in "-._~" for c in verifier)


def test_compute_code_challenge_known_rfc_test_vector():
    """
    Validates against the official RFC 7636 Appendix B test vector:
    code_verifier:  dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
    code_challenge: E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
    """
    rfc_verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    expected_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

    actual_challenge = compute_code_challenge(rfc_verifier)
    assert actual_challenge == expected_challenge


def test_signed_state_lifecycle():
    secret = "test-secret-at-least-32-bytes-long-super-secure"
    payload = {"code_verifier": "abc123xyz456", "redirect_url": "/dashboard"}

    state = create_signed_state(payload, secret_key=secret)
    assert isinstance(state, str)
    assert "." in state

    decoded = verify_signed_state(state, secret_key=secret, max_age_seconds=600)
    assert decoded["code_verifier"] == "abc123xyz456"
    assert decoded["redirect_url"] == "/dashboard"
    assert "state_id" in decoded
    assert "ts" in decoded


def test_signed_state_tampering_fails():
    secret = "test-secret-at-least-32-bytes-long-super-secure"
    state = create_signed_state({"data": "original"}, secret_key=secret)

    # Tamper with signature
    parts = state.split(".")
    tampered_sig = parts[0] + "." + parts[1][:-2] + "xx"
    with pytest.raises(ValueError, match="Invalid state signature"):
        verify_signed_state(tampered_sig, secret_key=secret)

    # Tamper with payload
    tampered_data = "aW52YWxpZA" + "." + parts[1]
    with pytest.raises(ValueError, match="Invalid state signature"):
        verify_signed_state(tampered_data, secret_key=secret)


def test_signed_state_expiration():
    secret = "test-secret-at-least-32-bytes-long-super-secure"
    payload = {"code_verifier": "abc", "ts": int(time.time()) - 700}
    expired_state = create_signed_state(payload, secret_key=secret)

    with pytest.raises(ValueError, match="State token has expired"):
        verify_signed_state(expired_state, secret_key=secret, max_age_seconds=600)


def test_signed_state_malformed():
    secret = "test-secret-at-least-32-bytes-long-super-secure"
    with pytest.raises(ValueError, match="Malformed state token"):
        verify_signed_state("not-a-valid-token", secret_key=secret)

    with pytest.raises(ValueError, match="Malformed state token"):
        verify_signed_state("part1.part2.part3", secret_key=secret)
