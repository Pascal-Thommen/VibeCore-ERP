"""Tests for Bancard vPOS cryptographic tokens and signed webhooks."""

import hashlib
import time
from decimal import Decimal
import pytest

from bancard.crypto import (
    format_bancard_amount,
    generate_card_new_token,
    generate_charge_token,
    generate_confirmation_hmac_sha256,
    generate_confirmation_token_confirm,
    generate_confirmation_token_response_code,
    generate_rollback_token,
    generate_single_buy_token,
    sign_vibecore_webhook,
    verify_bancard_confirmation_token,
    verify_vibecore_webhook_signature,
)


def test_format_bancard_amount():
    assert format_bancard_amount(45000) == "45000.00"
    assert format_bancard_amount(45000.5) == "45000.50"
    assert format_bancard_amount(Decimal("123.456")) == "123.46"
    assert format_bancard_amount("500000.00") == "500000.00"


def test_generate_single_buy_token():
    private_key = "secret_key_123"
    shop_process_id = 10001
    amount = 45000
    currency = "PYG"

    expected_raw = f"{private_key}{shop_process_id}45000.00{currency}"
    expected_token = hashlib.md5(expected_raw.encode("utf-8")).hexdigest()

    token = generate_single_buy_token(private_key, shop_process_id, amount, currency)
    assert token == expected_token
    assert len(token) == 32


def test_generate_rollback_token():
    private_key = "secret_key_123"
    shop_process_id = 10001

    expected_raw = f"{private_key}{shop_process_id}rollback0.00"
    expected_token = hashlib.md5(expected_raw.encode("utf-8")).hexdigest()

    token = generate_rollback_token(private_key, shop_process_id)
    assert token == expected_token


def test_generate_card_new_token():
    private_key = "secret_key_123"
    card_id = 1
    user_id = "usr_tenant_42"

    expected_raw = f"{private_key}{card_id}{user_id}request_user_card"
    expected_token = hashlib.md5(expected_raw.encode("utf-8")).hexdigest()

    token = generate_card_new_token(private_key, card_id, user_id)
    assert token == expected_token


def test_generate_charge_token():
    private_key = "secret_key_123"
    shop_process_id = 10002
    amount = 75000
    currency = "PYG"
    alias_token = "alias_tok_999888"

    expected_raw = f"{private_key}{shop_process_id}charge75000.00{currency}{alias_token}"
    expected_token = hashlib.md5(expected_raw.encode("utf-8")).hexdigest()

    token = generate_charge_token(private_key, shop_process_id, amount, currency, alias_token)
    assert token == expected_token


def test_verify_bancard_confirmation_token_confirm_format():
    private_key = "test_priv"
    shop_process_id = 555
    amount = 45000
    currency = "PYG"

    valid_token = generate_confirmation_token_confirm(private_key, shop_process_id, amount, currency)
    assert verify_bancard_confirmation_token(private_key, shop_process_id, amount, currency, valid_token)


def test_verify_bancard_confirmation_token_response_code_format():
    private_key = "test_priv"
    shop_process_id = 555
    amount = 45000
    currency = "PYG"
    response_code = "00"

    valid_token = generate_confirmation_token_response_code(private_key, shop_process_id, response_code, amount)
    assert verify_bancard_confirmation_token(
        private_key, shop_process_id, amount, currency, valid_token, response_code=response_code
    )


def test_verify_bancard_confirmation_token_hmac_format():
    private_key = "test_priv"
    shop_process_id = 555
    amount = 45000
    currency = "PYG"
    response_code = "00"

    valid_hmac = generate_confirmation_hmac_sha256(private_key, shop_process_id, amount, currency, response_code)
    assert verify_bancard_confirmation_token(
        private_key, shop_process_id, amount, currency, valid_hmac, response_code=response_code
    )


def test_verify_bancard_confirmation_token_invalid():
    private_key = "test_priv"
    shop_process_id = 555
    amount = 45000
    currency = "PYG"

    # Completely wrong token
    assert not verify_bancard_confirmation_token(
        private_key, shop_process_id, amount, currency, "deadbeef12345678"
    )

    # Empty token
    assert not verify_bancard_confirmation_token(
        private_key, shop_process_id, amount, currency, ""
    )

    # Tampered amount
    valid_token = generate_confirmation_token_confirm(private_key, shop_process_id, amount, currency)
    assert not verify_bancard_confirmation_token(
        private_key, shop_process_id, 99999, currency, valid_token
    )


def test_sign_and_verify_vibecore_webhook():
    secret = "vibecore_top_secret_2026"
    payload = b'{"event":"test.payment.approved","amount":"45000"}'
    ts = int(time.time())

    sig_header = sign_vibecore_webhook(secret, payload, timestamp=ts)
    assert sig_header.startswith(f"t={ts},v1=")

    # Verification passes
    assert verify_vibecore_webhook_signature(secret, payload, sig_header, current_time=ts)


def test_verify_vibecore_webhook_replay_protection():
    secret = "vibecore_top_secret_2026"
    payload = b'{"event":"test"}'
    old_ts = int(time.time()) - 400  # 400 seconds ago (> 300s max_age)

    sig_header = sign_vibecore_webhook(secret, payload, timestamp=old_ts)
    assert not verify_vibecore_webhook_signature(secret, payload, sig_header, max_age_seconds=300)


def test_verify_vibecore_webhook_tampered_payload():
    secret = "vibecore_top_secret_2026"
    payload = b'{"event":"test"}'
    ts = int(time.time())

    sig_header = sign_vibecore_webhook(secret, payload, timestamp=ts)

    tampered_payload = b'{"event":"test","tampered":true}'
    assert not verify_vibecore_webhook_signature(secret, tampered_payload, sig_header, current_time=ts)


def test_verify_vibecore_webhook_edge_cases():
    payload = b'{"event":"test"}'
    assert not verify_vibecore_webhook_signature("", payload, "t=123,v1=abc")
    assert not verify_vibecore_webhook_signature("sec", payload, "")
    assert not verify_vibecore_webhook_signature("sec", payload, "invalid_format")
    assert not verify_vibecore_webhook_signature("sec", payload, "t=notanint,v1=abc")
    assert not verify_vibecore_webhook_signature("sec", payload, "t=123")
    assert not verify_vibecore_webhook_signature("sec", payload, "v1=abc")
