"""
Tests for cryptographic signature verification, replay protection, and cent currency conversion.
"""

import hashlib
import hmac
import time

from stripe_adapter.client import StripeClient
from stripe_adapter.models import CurrencyHelper

TEST_SECRET = "whsec_test_secret_abc123"


def test_compute_webhook_signature():
    payload = b'{"id": "evt_test123", "type": "checkout.session.completed"}'
    timestamp = 1729000000

    sig = StripeClient.compute_webhook_signature(payload, TEST_SECRET, timestamp)

    expected_signed = f"{timestamp}.".encode() + payload
    expected = hmac.new(TEST_SECRET.encode("utf-8"), expected_signed, hashlib.sha256).hexdigest()

    assert sig == expected
    assert len(sig) == 64


def test_verify_webhook_signature_valid():
    payload = b'{"id": "evt_valid", "type": "payment_intent.succeeded"}'
    current_time = int(time.time())
    sig = StripeClient.compute_webhook_signature(payload, TEST_SECRET, current_time)
    header = f"t={current_time},v1={sig}"

    is_valid, calculated_sig, data = StripeClient.verify_webhook_signature(
        payload=payload,
        signature_header=header,
        secret=TEST_SECRET,
        tolerance=300,
    )

    assert is_valid is True
    assert calculated_sig == sig
    assert data.get("id") == "evt_valid"
    assert data.get("type") == "payment_intent.succeeded"


def test_verify_webhook_signature_tampered_payload():
    payload = b'{"id": "evt_original", "type": "payment_intent.succeeded"}'
    current_time = int(time.time())
    sig = StripeClient.compute_webhook_signature(payload, TEST_SECRET, current_time)
    header = f"t={current_time},v1={sig}"

    tampered_payload = b'{"id": "evt_original", "type": "payment_intent.succeeded", "admin": true}'
    is_valid, _, data = StripeClient.verify_webhook_signature(
        payload=tampered_payload,
        signature_header=header,
        secret=TEST_SECRET,
        tolerance=300,
    )

    assert is_valid is False
    assert data == {}


def test_verify_webhook_signature_wrong_secret():
    payload = b'{"id": "evt_secret", "type": "payment_intent.succeeded"}'
    current_time = int(time.time())
    sig = StripeClient.compute_webhook_signature(payload, "whsec_wrong_secret", current_time)
    header = f"t={current_time},v1={sig}"

    is_valid, _, data = StripeClient.verify_webhook_signature(
        payload=payload,
        signature_header=header,
        secret=TEST_SECRET,
        tolerance=300,
    )

    assert is_valid is False
    assert data == {}


def test_verify_webhook_replay_protection():
    payload = b'{"id": "evt_replay", "type": "payment_intent.succeeded"}'
    old_time = int(time.time()) - 600  # 10 minutes ago, tolerance is 300s
    sig = StripeClient.compute_webhook_signature(payload, TEST_SECRET, old_time)
    header = f"t={old_time},v1={sig}"

    is_valid, _, data = StripeClient.verify_webhook_signature(
        payload=payload,
        signature_header=header,
        secret=TEST_SECRET,
        tolerance=300,
    )

    assert is_valid is False
    assert data == {}


def test_verify_webhook_multiple_v1_signatures():
    payload = b'{"id": "evt_multi", "type": "checkout.session.completed"}'
    current_time = int(time.time())
    valid_sig = StripeClient.compute_webhook_signature(payload, TEST_SECRET, current_time)
    dummy_sig = "0000000000000000000000000000000000000000000000000000000000000000"
    header = f"t={current_time},v1={dummy_sig},v1={valid_sig}"

    is_valid, calculated_sig, data = StripeClient.verify_webhook_signature(
        payload=payload,
        signature_header=header,
        secret=TEST_SECRET,
        tolerance=300,
    )

    assert is_valid is True
    assert calculated_sig == valid_sig
    assert data.get("id") == "evt_multi"


def test_verify_webhook_malformed_header():
    payload = b'{"id": "evt_malformed"}'
    for bad_header in ["", "invalid_header", "t=notanumber,v1=123", "t=12345", "v1=12345"]:
        is_valid, _, data = StripeClient.verify_webhook_signature(
            payload=payload,
            signature_header=bad_header,
            secret=TEST_SECRET,
        )
        assert is_valid is False


def test_currency_cent_conversions():
    # 2 decimal places (USD, EUR, GBP)
    assert CurrencyHelper.amount_to_cents(10.50, "USD") == 1050
    assert CurrencyHelper.cents_to_amount(1050, "USD") == 10.50

    assert CurrencyHelper.amount_to_cents(99.99, "EUR") == 9999
    assert CurrencyHelper.cents_to_amount(9999, "EUR") == 99.99

    assert CurrencyHelper.amount_to_cents(0.01, "USD") == 1
    assert CurrencyHelper.cents_to_amount(1, "USD") == 0.01

    # Zero decimal places (JPY, PYG)
    assert CurrencyHelper.amount_to_cents(15000, "JPY") == 15000
    assert CurrencyHelper.cents_to_amount(15000, "JPY") == 15000.0

    assert CurrencyHelper.amount_to_cents(500000, "PYG") == 500000
    assert CurrencyHelper.cents_to_amount(500000, "PYG") == 500000.0

    # 3 decimal places (KWD)
    assert CurrencyHelper.amount_to_cents(5.125, "KWD") == 5125
    assert CurrencyHelper.cents_to_amount(5125, "KWD") == 5.125
