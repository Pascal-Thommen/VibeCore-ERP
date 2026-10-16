"""Cryptographic functions for Bancard vPOS 2.0 tokens and signed VibeCore webhooks."""

from __future__ import annotations

import hashlib
import hmac
import time
from decimal import Decimal
from typing import Optional, Union


def format_bancard_amount(amount: Union[Decimal, float, int, str]) -> str:
    """Format amount strictly with 2 decimal places and dot separator (e.g. '45000.00')."""
    d = Decimal(str(amount))
    return f"{d:.2f}"


def generate_single_buy_token(
    private_key: str,
    shop_process_id: Union[int, str],
    amount: Union[Decimal, float, int, str],
    currency: str,
) -> str:
    """Calculate MD5 token for Bancard vPOS single_buy: MD5(private_key + shop_process_id + amount + currency)."""
    amount_str = format_bancard_amount(amount)
    raw = f"{private_key}{shop_process_id}{amount_str}{currency}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def generate_rollback_token(
    private_key: str,
    shop_process_id: Union[int, str],
) -> str:
    """Calculate MD5 token for Bancard rollback: MD5(private_key + shop_process_id + 'rollback' + '0.00')."""
    raw = f"{private_key}{shop_process_id}rollback0.00"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def generate_card_new_token(
    private_key: str,
    card_id: Union[int, str],
    user_id: Union[int, str],
) -> str:
    """Calculate MD5 token for Bancard Catastro cards/new: MD5(private_key + card_id + user_id + 'request_user_card')."""
    raw = f"{private_key}{card_id}{user_id}request_user_card"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def generate_charge_token(
    private_key: str,
    shop_process_id: Union[int, str],
    amount: Union[Decimal, float, int, str],
    currency: str,
    alias_token: str,
) -> str:
    """Calculate MD5 token for tokenized charge: MD5(private_key + shop_process_id + 'charge' + amount + currency + alias_token)."""
    amount_str = format_bancard_amount(amount)
    raw = f"{private_key}{shop_process_id}charge{amount_str}{currency}{alias_token}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def generate_confirmation_token_confirm(
    private_key: str,
    shop_process_id: Union[int, str],
    amount: Union[Decimal, float, int, str],
    currency: str,
) -> str:
    """Confirmation hash format A: MD5(private_key + shop_process_id + 'confirm' + amount + currency)."""
    amount_str = format_bancard_amount(amount)
    raw = f"{private_key}{shop_process_id}confirm{amount_str}{currency}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def generate_confirmation_token_response_code(
    private_key: str,
    shop_process_id: Union[int, str],
    response_code: str,
    amount: Union[Decimal, float, int, str],
) -> str:
    """Confirmation hash format B: MD5(private_key + shop_process_id + response_code + amount)."""
    amount_str = format_bancard_amount(amount)
    raw = f"{private_key}{shop_process_id}{response_code}{amount_str}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def generate_confirmation_hmac_sha256(
    private_key: str,
    shop_process_id: Union[int, str],
    amount: Union[Decimal, float, int, str],
    currency: str,
    response_code: str,
) -> str:
    """HMAC-SHA256 signature for Bancard confirmation webhooks."""
    amount_str = format_bancard_amount(amount)
    message = f"{shop_process_id}:{amount_str}:{currency}:{response_code}".encode("utf-8")
    return hmac.new(private_key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_bancard_confirmation_token(
    private_key: str,
    shop_process_id: Union[int, str],
    amount: Union[Decimal, float, int, str],
    currency: str,
    received_token: str,
    response_code: Optional[str] = None,
) -> bool:
    """
    Verify incoming Bancard confirmation webhook security hash.
    Checks against candidate Bancard formats with constant-time equality.
    """
    if not received_token:
        return False

    received_token_clean = received_token.strip().lower()

    # Candidate 1: Standard confirm hash
    cand1 = generate_confirmation_token_confirm(private_key, shop_process_id, amount, currency).lower()
    if hmac.compare_digest(cand1, received_token_clean):
        return True

    # Candidate 2: Response code hash (if provided)
    if response_code is not None:
        cand2 = generate_confirmation_token_response_code(private_key, shop_process_id, response_code, amount).lower()
        if hmac.compare_digest(cand2, received_token_clean):
            return True

        # Candidate 3: HMAC-SHA256
        cand3 = generate_confirmation_hmac_sha256(private_key, shop_process_id, amount, currency, response_code).lower()
        if hmac.compare_digest(cand3, received_token_clean):
            return True

    return False


def sign_vibecore_webhook(
    secret: str,
    payload_bytes: bytes,
    timestamp: Optional[int] = None,
) -> str:
    """
    Generate standard VibeCore HMAC-SHA256 webhook signature header.
    Format: 't=<timestamp>,v1=<hex_signature>'
    """
    ts = timestamp if timestamp is not None else int(time.time())
    body_str = payload_bytes.decode("utf-8") if isinstance(payload_bytes, bytes) else str(payload_bytes)
    signed_payload = f"v1:{ts}:{body_str}".encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={signature}"


def verify_vibecore_webhook_signature(
    secret: str,
    payload_bytes: bytes,
    signature_header: str,
    max_age_seconds: int = 300,
    current_time: Optional[int] = None,
) -> bool:
    """Verify standard VibeCore HMAC-SHA256 webhook signature with replay protection."""
    if not signature_header or not secret:
        return False

    now = current_time if current_time is not None else int(time.time())
    parts = dict(item.strip().split("=", 1) for item in signature_header.split(",") if "=" in item)

    ts_str = parts.get("t")
    received_sig = parts.get("v1")

    if not ts_str or not received_sig:
        return False

    try:
        ts = int(ts_str)
    except ValueError:
        return False

    # Check clock skew / replay attack
    if abs(now - ts) > max_age_seconds:
        return False

    body_str = payload_bytes.decode("utf-8") if isinstance(payload_bytes, bytes) else str(payload_bytes)
    signed_payload = f"v1:{ts}:{body_str}".encode("utf-8")
    expected_sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()

    return hmac.compare_digest(expected_sig.lower(), received_sig.strip().lower())
