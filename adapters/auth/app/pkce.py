"""
VibeCore ERP Auth Adapter - PKCE & Cryptographic State Helper (RFC 7636).
Implements Proof Key for Code Exchange (S256) and tamper-proof HMAC CSRF state tokens.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from typing import Any


def generate_code_verifier(byte_length: int = 64) -> str:
    """
    Generates a cryptographically random PKCE code verifier (RFC 7636 Section 4.1).
    Produces a URL-safe string with length between 43 and 128 characters.
    """
    verifier = secrets.token_urlsafe(byte_length)
    if len(verifier) < 43 or len(verifier) > 128:
        # Fallback to precise slicing within RFC bounds
        verifier = verifier[:128]
        if len(verifier) < 43:
            verifier = verifier.ljust(43, "x")
    return verifier


def compute_code_challenge(code_verifier: str) -> str:
    """
    Computes code_challenge = BASE64URL-ENCODE(SHA256(code_verifier)) without padding (RFC 7636 Section 4.2).
    """
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return challenge


def create_signed_state(payload: dict[str, Any], secret_key: str) -> str:
    """
    Creates a tamper-proof state token by signing payload with HMAC-SHA256.
    Includes state_id and timestamp for expiration validation.
    """
    data = dict(payload)
    if "state_id" not in data:
        data["state_id"] = uuid.uuid4().hex
    if "ts" not in data:
        data["ts"] = int(time.time())

    json_bytes = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    data_b64 = base64.urlsafe_b64encode(json_bytes).decode("ascii").rstrip("=")

    signature = hmac.new(
        secret_key.encode("utf-8"), data_b64.encode("ascii"), hashlib.sha256
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")

    return f"{data_b64}.{sig_b64}"


def verify_signed_state(
    signed_state: str, secret_key: str, max_age_seconds: int = 600
) -> dict[str, Any]:
    """
    Verifies the HMAC signature and timestamp of a signed state token.
    Raises ValueError if invalid, tampered with, or expired.
    """
    if not signed_state or "." not in signed_state:
        raise ValueError("Malformed state token format.")

    parts = signed_state.split(".")
    if len(parts) != 2:
        raise ValueError("Malformed state token: incorrect segments.")

    data_b64, sig_b64 = parts[0], parts[1]

    # Recompute signature
    expected_sig = hmac.new(
        secret_key.encode("utf-8"), data_b64.encode("ascii"), hashlib.sha256
    ).digest()
    expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode("ascii").rstrip("=")

    if not hmac.compare_digest(sig_b64, expected_sig_b64):
        raise ValueError("Invalid state signature: potential CSRF tampering detected.")

    # Decode JSON payload
    padded_data = data_b64 + "=" * (-len(data_b64) % 4)
    try:
        json_bytes = base64.urlsafe_b64decode(padded_data.encode("ascii"))
        payload = json.loads(json_bytes.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to decode state payload: {e}") from e

    # Validate expiration
    ts = payload.get("ts")
    if not isinstance(ts, (int, float)):
        raise TypeError("Invalid timestamp type in state token.")

    now = time.time()
    if now - ts > max_age_seconds:
        raise ValueError("State token has expired. Please initiate login again.")
    if ts > now + 30:  # 30 seconds future tolerance for clock skew
        raise ValueError("State token timestamp is in the future.")

    return payload
