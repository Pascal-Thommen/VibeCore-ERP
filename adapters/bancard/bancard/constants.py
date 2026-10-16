"""Constants for Bancard vPOS 2.0 and Paraguay Catastro QR integration."""

from enum import Enum


class BancardEnvironment(str, Enum):
    STAGING = "staging"
    PRODUCTION = "production"


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVERSED = "REVERSED"


class PaymentMethod(str, Enum):
    SINGLE_BUY = "single_buy"
    TOKEN_CHARGE = "token_charge"
    CARDS_NEW = "cards_new"
    CATASTRO_QR = "catastro_qr"


# ISO 4217 Currency Codes
CURRENCY_PYG = "PYG"
CURRENCY_USD = "USD"
CURRENCY_CODE_PYG = "600"
CURRENCY_CODE_USD = "840"

# Bancard vPOS Official Response Codes
RESPONSE_CODE_APPROVED = "00"
RESPONSE_CODE_HONOR = "05"
RESPONSE_CODE_INVALID_TX = "12"
RESPONSE_CODE_INVALID_CARD = "15"
RESPONSE_CODE_INSUFFICIENT_FUNDS = "51"
RESPONSE_CODE_CALL_ISSUER = "54"
RESPONSE_CODE_EXPIRED_CARD = "57"
RESPONSE_CODE_TIMEOUT = "99"

# Bancard vPOS Endpoints
ENDPOINT_SINGLE_BUY = "/vpos/api/0.3/single_buy"
ENDPOINT_ROLLBACK = "/vpos/api/0.3/single_buy/rollback"
ENDPOINT_CARDS_NEW = "/vpos/api/0.3/cards/new"
ENDPOINT_CHARGE = "/vpos/api/0.3/charge"
ENDPOINT_CONFIRMATION = "/vpos/api/0.3/single_buy/confirm"

# EMVCo Tag Definitions for Paraguayan QR
EMV_TAG_PAYLOAD_FORMAT_INDICATOR = "00"
EMV_TAG_POINT_OF_INITIATION_METHOD = "01"
EMV_TAG_MERCHANT_ACCOUNT_INFORMATION = "26"
EMV_TAG_MERCHANT_CATEGORY_CODE = "52"
EMV_TAG_TRANSACTION_CURRENCY = "53"
EMV_TAG_TRANSACTION_AMOUNT = "54"
EMV_TAG_COUNTRY_CODE = "58"
EMV_TAG_MERCHANT_NAME = "59"
EMV_TAG_MERCHANT_CITY = "60"
EMV_TAG_ADDITIONAL_DATA_FIELD = "62"
EMV_TAG_CRC = "63"

# Default EMVCo Values for Paraguay Bancard QR
EMV_DEFAULT_FORMAT = "01"
EMV_POINT_DYNAMIC = "12"
EMV_DEFAULT_COUNTRY = "PY"
EMV_DEFAULT_MCC = "0000"
EMV_DEFAULT_MERCHANT_NAME = "VibeCore Pay"
EMV_DEFAULT_MERCHANT_CITY = "Asuncion"
EMV_BANCARD_GUI = "py.com.bancard"

# Signature & Header constants
HEADER_IDEMPOTENCY_KEY = "Idempotency-Key"
HEADER_CORRELATION_ID = "X-Correlation-ID"
HEADER_VIBECORE_SIGNATURE = "X-VibeCore-Signature"
HEADER_VIBECORE_TIMESTAMP = "X-VibeCore-Timestamp"
