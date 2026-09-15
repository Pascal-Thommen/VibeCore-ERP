from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.main import app
from app.schemas.core_schemas import DocumentCreate, TaxCreate


@pytest.fixture
def electronic_document_payload() -> dict[str, object]:
    return {
        "document_type": "INVOICE",
        "direction": "SALES",
        "created_by_actor": "AI_AGENT",
        "partner_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "issued_at": "2026-09-15T09:30:00-04:00",
        "currency_code": "PYG",
        "issuer_ruc": "1234567",
        "issuer_dv": "1",
        "issuer_legal_name": "VibeCore S.A.",
        "is_electronic": True,
        "timbrado_number": "12345678",
        "establishment_code": "001",
        "point_of_issue_code": "001",
        "sifen_document_type": "01",
        "sifen_emission_type": "1",
        "sifen_document_number": "0000001",
        "sifen_cdc": "1" * 44,
        "sifen_security_code": "123456789",
        "items": [
            {
                "tax_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "description": "Maize",
                "unit_of_measure": "KGM",
                "quantity": "1",
                "unit_price": "10",
            }
        ],
    }


def test_document_schema_rejects_incomplete_or_malformed_sifen_identity(
    electronic_document_payload: dict[str, object],
) -> None:
    malformed_cdc = deepcopy(electronic_document_payload)
    malformed_cdc["sifen_cdc"] = "1" * 43
    with pytest.raises(ValidationError):
        DocumentCreate.model_validate(malformed_cdc)

    incomplete = deepcopy(electronic_document_payload)
    incomplete.pop("timbrado_number")
    with pytest.raises(ValidationError):
        DocumentCreate.model_validate(incomplete)

    duplicate_security_number = deepcopy(electronic_document_payload)
    duplicate_security_number["sifen_security_code"] = "000000001"
    with pytest.raises(ValidationError):
        DocumentCreate.model_validate(duplicate_security_number)


def test_financial_float_and_non_sifen_iva_rate_are_rejected() -> None:
    with pytest.raises(ValidationError):
        TaxCreate.model_validate({"code": "IVA_7", "name": "IVA 7%", "rate": 7.0})


def test_core_resource_routes_are_registered_under_v1() -> None:
    paths = {route.path for route in app.routes}
    assert {
        "/api/v1/partners",
        "/api/v1/accounts",
        "/api/v1/taxes",
        "/api/v1/products",
        "/api/v1/documents",
    } <= paths
