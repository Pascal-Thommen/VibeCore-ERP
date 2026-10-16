"""Paraguay Catastro QR & EMVCo Dynamic QR Generator for Bancard (PYG)."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Union
import segno

from app.bancard.constants import (
    CURRENCY_CODE_PYG,
    EMV_BANCARD_GUI,
    EMV_DEFAULT_COUNTRY,
    EMV_DEFAULT_FORMAT,
    EMV_DEFAULT_MCC,
    EMV_DEFAULT_MERCHANT_CITY,
    EMV_DEFAULT_MERCHANT_NAME,
    EMV_POINT_DYNAMIC,
    EMV_TAG_ADDITIONAL_DATA_FIELD,
    EMV_TAG_COUNTRY_CODE,
    EMV_TAG_CRC,
    EMV_TAG_MERCHANT_ACCOUNT_INFORMATION,
    EMV_TAG_MERCHANT_CATEGORY_CODE,
    EMV_TAG_MERCHANT_NAME,
    EMV_TAG_MERCHANT_CITY,
    EMV_TAG_PAYLOAD_FORMAT_INDICATOR,
    EMV_TAG_POINT_OF_INITIATION_METHOD,
    EMV_TAG_TRANSACTION_AMOUNT,
    EMV_TAG_TRANSACTION_CURRENCY,
)


def compute_emvco_crc(data: str) -> str:
    """
    Compute standard EMVCo CRC-16 (CCITT, polynomial 0x1021, initial value 0xFFFF).
    Returns 4-digit hexadecimal uppercase string.
    """
    crc = 0xFFFF
    for byte in data.encode("iso-8859-1"):
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def build_tlv(tag: str, value: str) -> str:
    """Build TLV entry: Tag (2 digits) + Length (2 digits) + Value."""
    length = len(value)
    if length > 99:
        raise ValueError(f"TLV value exceeds maximum length 99 for tag {tag}")
    return f"{tag}{length:02d}{value}"


def build_bancard_catastro_qr_payload(
    shop_process_id: Union[int, str],
    amount: Union[Decimal, float, int, str],
    merchant_id: str = "vibecore_merchant_01",
    merchant_name: str = EMV_DEFAULT_MERCHANT_NAME,
    merchant_city: str = EMV_DEFAULT_MERCHANT_CITY,
    description: Optional[str] = None,
) -> str:
    """
    Construct an official EMVCo-compliant dynamic QR payload for Bancard in Paraguay.
    Currency is strictly Guaranies (PYG = 600).
    """
    # Format amount: in Guaranies integer amounts are standard
    amount_dec = Decimal(str(amount))
    if amount_dec <= 0:
        raise ValueError("Transaction amount must be strictly positive")

    # In PYG, amounts are typically whole numbers without decimals
    amount_str = f"{int(amount_dec)}" if amount_dec == amount_dec.to_integral() else f"{amount_dec:.2f}"

    # Build sub-TLV for Tag 26 (Merchant Account Information)
    sub26_gui = build_tlv("00", EMV_BANCARD_GUI)
    sub26_mid = build_tlv("01", str(merchant_id))
    sub26_pid = build_tlv("02", str(shop_process_id))
    tag26_value = f"{sub26_gui}{sub26_mid}{sub26_pid}"

    # Build sub-TLV for Tag 62 (Additional Data Field)
    sub62_ref = build_tlv("05", str(shop_process_id))
    tag62_value = sub62_ref

    # Assemble elements in order
    elements = [
        build_tlv(EMV_TAG_PAYLOAD_FORMAT_INDICATOR, EMV_DEFAULT_FORMAT),
        build_tlv(EMV_TAG_POINT_OF_INITIATION_METHOD, EMV_POINT_DYNAMIC),
        build_tlv(EMV_TAG_MERCHANT_ACCOUNT_INFORMATION, tag26_value),
        build_tlv(EMV_TAG_MERCHANT_CATEGORY_CODE, EMV_DEFAULT_MCC),
        build_tlv(EMV_TAG_TRANSACTION_CURRENCY, CURRENCY_CODE_PYG),
        build_tlv(EMV_TAG_TRANSACTION_AMOUNT, amount_str),
        build_tlv(EMV_TAG_COUNTRY_CODE, EMV_DEFAULT_COUNTRY),
        build_tlv(EMV_TAG_MERCHANT_NAME, merchant_name[:25]),
        build_tlv(EMV_TAG_MERCHANT_CITY, merchant_city[:15]),
        build_tlv(EMV_TAG_ADDITIONAL_DATA_FIELD, tag62_value),
    ]

    base_payload = "".join(elements)
    # Append Tag 63 with length 04 for checksum
    prefix_for_crc = f"{base_payload}{EMV_TAG_CRC}04"
    crc_value = compute_emvco_crc(prefix_for_crc)
    full_payload = f"{prefix_for_crc}{crc_value}"

    return full_payload


def verify_emvco_qr_payload(payload: str) -> bool:
    """Verify format and CRC16 checksum of an EMVCo QR code string."""
    if len(payload) < 20 or not payload.startswith("000201"):
        return False
    if "6304" not in payload:
        return False

    idx = payload.rfind("6304")
    if idx == -1 or len(payload) != idx + 8:
        return False

    data_to_verify = payload[: idx + 4]
    expected_crc = payload[idx + 4 :].upper()
    actual_crc = compute_emvco_crc(data_to_verify)

    return expected_crc == actual_crc


def generate_qr_image_data_uri(payload: str, scale: int = 5) -> str:
    """Generate PNG Base64 data URI from payload string using segno."""
    qr = segno.make(payload, error="m")
    return qr.png_data_uri(scale=scale)


def generate_qr_svg_string(payload: str, scale: int = 5) -> str:
    """Generate SVG string representation of QR code."""
    qr = segno.make(payload, error="m")
    import io
    buff = io.BytesIO()
    qr.save(buff, kind="svg", scale=scale)
    return buff.getvalue().decode("utf-8")
