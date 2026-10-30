from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.crud.core_crud import (
    DocumentNotEditableError,
    PartnerDirectionError,
    TaxScopeError,
    calculate_paraguayan_iva,
    create_document,
)
from app.main import app
from app.models import Partner, Tax
from app.schemas.core_schemas import DocumentCreate, ProductCreate, TaxCreate


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
    paths = {route.path for route in app.routes if hasattr(route, "path")} | set(
        app.openapi().get("paths", {}).keys()
    )
    assert {
        "/api/v1/partners",
        "/api/v1/accounts",
        "/api/v1/taxes",
        "/api/v1/products",
        "/api/v1/documents",
    } <= paths
    assert "/api/v1/documents/items/{item_id}" not in paths
    assert "/api/v1/documents/{document_id}/items" not in paths


def test_product_schema_rejects_removed_shell_stock_and_weight_fields() -> None:
    product = ProductCreate.model_validate(
        {
            "sku": "SRV-001",
            "name": "Beratungsleistung",
            "unit_of_measure": "UNI",
            "standard_price": "110000",
        }
    )
    assert product.sku == "SRV-001"

    for removed_field in ("is_stock_item", "valuation_rate", "weight_per_unit", "weight_unit"):
        with pytest.raises(ValidationError):
            ProductCreate.model_validate(
                {
                    "sku": "SRV-001",
                    "name": "Beratungsleistung",
                    "unit_of_measure": "UNI",
                    removed_field: "1",
                }
            )


def test_paraguayan_iva_gross_inclusive_calculation_ley_6380_19() -> None:
    from decimal import Decimal

    # IVA 10% in PYG: Brutto 110.000 Gs -> IVA = 110.000 / 11 = 10.000 Gs, Netto = 100.000 Gs
    net_10, tax_10, gross_10 = calculate_paraguayan_iva(
        Decimal("110000"), Decimal("10"), "PYG"
    )
    assert gross_10 == Decimal("110000")
    assert tax_10 == Decimal("10000")
    assert net_10 == Decimal("100000")
    assert net_10 + tax_10 == gross_10

    # IVA 5% in PYG: Brutto 105.000 Gs -> IVA = 105.000 / 21 = 5.000 Gs, Netto = 100.000 Gs
    net_5, tax_5, gross_5 = calculate_paraguayan_iva(
        Decimal("105000"), Decimal("5"), "PYG"
    )
    assert gross_5 == Decimal("105000")
    assert tax_5 == Decimal("5000")
    assert net_5 == Decimal("100000")
    assert net_5 + tax_5 == gross_5

    # PYG Rounding without centavos (e.g. 100.000 Gs at 10% IVA -> IVA = 9091 Gs, Net = 90909 Gs)
    net_odd, tax_odd, gross_odd = calculate_paraguayan_iva(
        Decimal("100000"), Decimal("10"), "PYG"
    )
    assert gross_odd == Decimal("100000")
    assert tax_odd == Decimal("9091")
    assert net_odd == Decimal("90909")
    assert net_odd + tax_odd == gross_odd
    assert tax_odd.as_tuple().exponent == 0
    assert net_odd.as_tuple().exponent == 0

    # Exenta 0% in PYG
    net_0, tax_0, gross_0 = calculate_paraguayan_iva(
        Decimal("50000"), Decimal("0"), "PYG"
    )
    assert gross_0 == Decimal("50000")
    assert tax_0 == Decimal("0")
    assert net_0 == Decimal("50000")


def test_create_document_applies_gross_inclusive_iva_and_rejects_invalid_states(
    electronic_document_payload: dict[str, object],
) -> None:
    import asyncio
    from decimal import Decimal
    from uuid import UUID

    partner_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    tax_10_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    tax_5_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    class InMemoryCoreSession:
        def __init__(self) -> None:
            self.partners = {
                partner_id: Partner(
                    id=partner_id,
                    ruc="80012345",
                    dv="6",
                    legal_name="Cliente S.A.",
                    is_customer=True,
                    is_supplier=False,
                    is_active=True,
                )
            }
            self.taxes = {
                tax_10_id: Tax(
                    id=tax_10_id,
                    code="IVA_10",
                    name="IVA 10%",
                    rate=Decimal("10"),
                    scope="BOTH",
                    is_active=True,
                ),
                tax_5_id: Tax(
                    id=tax_5_id,
                    code="IVA_5",
                    name="IVA 5%",
                    rate=Decimal("5"),
                    scope="SALES",
                    is_active=True,
                ),
            }
            self.documents: dict[UUID, object] = {}

        async def get(self, model: type, entity_id: UUID) -> object | None:
            if model is Partner:
                return self.partners.get(entity_id)
            if model is Tax:
                return self.taxes.get(entity_id)
            return self.documents.get(entity_id)

        def add(self, entity: object) -> None:
            if hasattr(entity, "document_type"):
                if getattr(entity, "id", None) is None:
                    entity.id = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
                entity.items = []
                self.documents[entity.id] = entity
            elif hasattr(entity, "line_total"):
                doc = self.documents[entity.document_id]
                doc.items.append(entity)

        async def flush(self) -> None:
            return None

        async def commit(self) -> None:
            return None

        async def delete(self, _entity: object) -> None:
            return None

        async def scalars(self, _statement: object) -> object:
            session_self = self

            class _Result:
                def one_or_none(self) -> object | None:
                    return next(iter(session_self.documents.values()), None)

            return _Result()

    session = InMemoryCoreSession()
    payload = deepcopy(electronic_document_payload)
    payload["items"] = [
        {
            "tax_id": str(tax_10_id),
            "description": "Soja Brutto 10%",
            "unit_of_measure": "UNI",
            "quantity": "1",
            "unit_price": "110000",
        },
        {
            "tax_id": str(tax_5_id),
            "description": "Maiz Brutto 5%",
            "unit_of_measure": "UNI",
            "quantity": "2",
            "unit_price": "105000",
        },
    ]
    doc_create = DocumentCreate.model_validate(payload)
    doc = asyncio.run(create_document(session, doc_create))  # type: ignore[arg-type]

    assert doc.status == "DRAFT"
    assert doc.subtotal == Decimal("300000")
    assert doc.tax_total == Decimal("20000")
    assert doc.total == Decimal("320000")
    assert doc.subtotal + doc.tax_total == doc.total
    assert doc.functional_subtotal == Decimal("300000")
    assert doc.functional_tax_total == Decimal("20000")
    assert doc.functional_total == Decimal("320000")

    # Error case: non-DRAFT document cannot be deleted
    from app.crud.core_crud import delete_document

    doc.status = "POSTED"
    with pytest.raises(DocumentNotEditableError):
        asyncio.run(delete_document(session, doc.id))  # type: ignore[arg-type]

    # Error case: PURCHASE document with customer-only partner fails with PartnerDirectionError
    purchase_payload = deepcopy(payload)
    purchase_payload["direction"] = "PURCHASE"
    purchase_create = DocumentCreate.model_validate(purchase_payload)
    with pytest.raises(PartnerDirectionError):
        asyncio.run(create_document(session, purchase_create))  # type: ignore[arg-type]

    # Error case: SALES tax on PURCHASE document fails with TaxScopeError
    session.partners[partner_id].is_supplier = True
    with pytest.raises(TaxScopeError):
        asyncio.run(create_document(session, purchase_create))  # type: ignore[arg-type]
