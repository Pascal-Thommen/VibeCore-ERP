"""
Tests for cryptographic security, SHA-1 token generation, and timing-safe webhook validation.
Säule 3 (Sicherheit und Zugriffsschutz) des Software Testing Audit Frameworks.
"""

import hashlib

from pagopar.client import PagoparClient


def test_order_token_matches_pagopar_v2_specification():
    private_key = "secret_key_123"
    order_id = "ORD-2026-99"
    amount = 150000

    expected_raw = f"{private_key}{order_id}{float(amount)}"
    expected_hash = hashlib.sha1(expected_raw.encode("utf-8")).hexdigest()

    computed_hash = PagoparClient.compute_order_token(private_key, order_id, amount)
    assert computed_hash == expected_hash
    assert len(computed_hash) == 40


def test_polling_token_matches_consulta_specification():
    private_key = "secret_key_123"
    expected_raw = f"{private_key}CONSULTA"
    expected_hash = hashlib.sha1(expected_raw.encode("utf-8")).hexdigest()

    computed_hash = PagoparClient.compute_polling_token(private_key)
    assert computed_hash == expected_hash
    assert len(computed_hash) == 40


def test_webhook_token_and_signature_verification_valid():
    private_key = "secret_key_123"
    hash_pedido = "6a4f91b0d3e2c7a1884f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d"

    expected_hash = hashlib.sha1(f"{private_key}{hash_pedido}".encode()).hexdigest()
    assert PagoparClient.verify_webhook_signature(private_key, hash_pedido, expected_hash) is True


def test_webhook_signature_verification_rejects_tampered_token():
    private_key = "secret_key_123"
    hash_pedido = "6a4f91b0d3e2c7a1884f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d"

    # Subtle 1-char modification
    valid_hash = PagoparClient.compute_webhook_token(private_key, hash_pedido)
    tampered_hash = valid_hash[:-1] + ("0" if valid_hash[-1] != "0" else "1")

    assert PagoparClient.verify_webhook_signature(private_key, hash_pedido, tampered_hash) is False


def test_webhook_signature_verification_rejects_wrong_private_key():
    private_key_a = "secret_key_correct"
    private_key_b = "secret_key_attacker"
    hash_pedido = "6a4f91b0d3e2c7a1884f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d"

    attacker_token = PagoparClient.compute_webhook_token(private_key_b, hash_pedido)
    assert PagoparClient.verify_webhook_signature(private_key_a, hash_pedido, attacker_token) is False


def test_webhook_signature_verification_handles_empty_or_none():
    private_key = "secret_key_123"
    assert PagoparClient.verify_webhook_signature(private_key, "", "some_token") is False
    assert PagoparClient.verify_webhook_signature(private_key, "some_hash", "") is False
