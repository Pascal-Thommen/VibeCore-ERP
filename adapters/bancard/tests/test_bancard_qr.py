"""Tests for Paraguay Catastro QR EMVCo generation and validation."""

from decimal import Decimal
import pytest

from bancard.qr import (
    build_bancard_catastro_qr_payload,
    build_tlv,
    compute_emvco_crc,
    generate_qr_image_data_uri,
    generate_qr_svg_string,
    verify_emvco_qr_payload,
)


def test_build_tlv():
    assert build_tlv("00", "01") == "000201"
    assert build_tlv("53", "600") == "5303600"
    with pytest.raises(ValueError):
        build_tlv("01", "A" * 105)


def test_compute_emvco_crc():
    # Known test sample
    sample = "00020101021226380014py.com.bancard0116test_merchant_015204000053036005405450005802PY5912VibeCore Pay6008Asuncion6304"
    crc = compute_emvco_crc(sample)
    assert len(crc) == 4
    assert crc.isalnum()


def test_build_and_verify_bancard_catastro_qr_payload():
    shop_process_id = 10001
    amount = 45000

    payload = build_bancard_catastro_qr_payload(
        shop_process_id=shop_process_id,
        amount=amount,
        merchant_name="VibeCore Pay",
        merchant_city="Asuncion",
    )

    # Starts with payload format indicator
    assert payload.startswith("000201")
    # Dynamic point of initiation
    assert "010212" in payload
    # Bancard GUI
    assert "py.com.bancard" in payload
    # Guaranies currency code 600
    assert "5303600" in payload
    # Amount 45000
    assert "540545000" in payload
    # Country PY
    assert "5802PY" in payload
    # Checksum Tag 63
    assert "6304" in payload

    # Verify EMVCo checksum
    assert verify_emvco_qr_payload(payload)


def test_verify_emvco_qr_corrupted():
    payload = build_bancard_catastro_qr_payload(
        shop_process_id=10001,
        amount=45000,
    )

    # Tamper with one character in the payload
    corrupted_char = "9" if payload[10] != "9" else "8"
    corrupted_payload = payload[:10] + corrupted_char + payload[11:]

    assert not verify_emvco_qr_payload(corrupted_payload)
    assert not verify_emvco_qr_payload("short_invalid_qr")
    assert not verify_emvco_qr_payload("000201without_checksum_tag")


def test_invalid_amount_rejected():
    with pytest.raises(ValueError):
        build_bancard_catastro_qr_payload(shop_process_id=1, amount=0)

    with pytest.raises(ValueError):
        build_bancard_catastro_qr_payload(shop_process_id=1, amount=-500)


def test_generate_qr_image_data_uri():
    payload = build_bancard_catastro_qr_payload(shop_process_id=10001, amount=45000)
    data_uri = generate_qr_image_data_uri(payload, scale=3)
    assert data_uri.startswith("data:image/png;base64,")
    assert len(data_uri) > 100


def test_generate_qr_svg_string():
    payload = build_bancard_catastro_qr_payload(shop_process_id=10001, amount=45000)
    svg = generate_qr_svg_string(payload, scale=3)
    assert "<svg" in svg
    assert "</svg>" in svg
