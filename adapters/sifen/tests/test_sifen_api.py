"""
End-to-end integration tests for SIFEN FastAPI server.
"""

from datetime import datetime
from decimal import Decimal
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient

from sifen.constants import (
    DTE_BOLETA_RESIMPLE,
    DTE_FACTURA_ELECTRONICA,
    OBLIGACION_IRE_GENERAL,
    OBLIGACION_IRE_RESIMPLE,
    TaxRegime,
)
from sifen.server import app

client = TestClient(app)


def test_health_endpoints() -> None:
    res1 = client.get("/health")
    assert res1.status_code == 200
    assert res1.json()["status"] == "healthy"

    res2 = client.get("/api/v1/sifen/health")
    assert res2.status_code == 200
    assert res2.json()["service"] == "sifen-adapter"


def test_resolve_endpoint_ire_general() -> None:
    payload = {
        "ruc": "80011111",
        "dv": "4",
        "legal_name": "Empresa General S.A.",
        "obligaciones": [OBLIGACION_IRE_GENERAL],
    }
    res = client.post("/api/v1/sifen/resolve", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["regime"] == TaxRegime.IRE_GENERAL
    assert data["dte_type"] == DTE_FACTURA_ELECTRONICA
    assert data["iva_applicable"] is True
    assert data["requires_iva_breakdown"] is True


def test_resolve_endpoint_ire_resimple() -> None:
    payload = {
        "ruc": "80076543",
        "dv": "2",
        "legal_name": "Negocio Resimple",
        "obligaciones": [OBLIGACION_IRE_RESIMPLE],
    }
    res = client.post("/api/v1/sifen/resolve", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["regime"] == TaxRegime.IRE_RESIMPLE
    assert data["dte_type"] == DTE_BOLETA_RESIMPLE
    assert data["iva_applicable"] is False


def test_resolve_endpoint_invalid_obligation() -> None:
    payload = {
        "ruc": "80011111",
        "dv": "4",
        "legal_name": "Sin Obligacion",
        "obligaciones": [999],
    }
    res = client.post("/api/v1/sifen/resolve", json=payload)
    assert res.status_code == 400


def test_generate_xml_endpoint() -> None:
    payload = {
        "header": {
            "timbrado_number": "87654321",
            "establishment_code": "001",
            "point_of_issue_code": "001",
            "document_number": "0000005",
            "issue_date": "2026-10-14T12:00:00",
            "security_code": "123456789",
            "issuer_ruc": "80011111",
            "issuer_dv": "4",
            "issuer_legal_name": "Empresa General S.A.",
            "currency": "PYG",
        },
        "items": [
            {
                "line_number": 1,
                "description": "Consultoria ERP",
                "quantity": 1,
                "unit_price": 5000000,
                "tax_rate": 10,
            }
        ],
        "profile": {
            "ruc": "80011111",
            "dv": "4",
            "legal_name": "Empresa General S.A.",
            "obligaciones": [OBLIGACION_IRE_GENERAL],
        },
    }
    res = client.post("/api/v1/sifen/generate-xml", json=payload)
    assert res.status_code == 200
    assert "application/xml" in res.headers["content-type"]
    root = ET.fromstring(res.text)
    assert root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}iTiDE").text == "1"
    assert root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dTotOpe").text == "5000000"


def test_sign_endpoint() -> None:
    payload = {
        "header": {
            "timbrado_number": "87654321",
            "establishment_code": "001",
            "point_of_issue_code": "001",
            "document_number": "0000010",
            "issue_date": "2026-10-14T12:00:00",
            "security_code": "123456789",
            "issuer_ruc": "80011111",
            "issuer_dv": "4",
            "issuer_legal_name": "Empresa General S.A.",
            "currency": "PYG",
        },
        "items": [
            {
                "line_number": 1,
                "description": "Servicio Cloud",
                "quantity": 2,
                "unit_price": 1000000,
                "tax_rate": 10,
            }
        ],
        "profile": {
            "ruc": "80011111",
            "dv": "4",
            "legal_name": "Empresa General S.A.",
            "obligaciones": [OBLIGACION_IRE_GENERAL],
        },
    }
    res = client.post("/api/v1/sifen/sign", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert len(data["cdc"]) == 44
    assert "https://ekuatia.set.gov.py/consultas-test/qr?" in data["qr_url"]
    assert "Signature" in data["xml_signed"]
    assert "gCamFuFD" in data["xml_signed"]


def test_sign_and_send_endpoint_with_simulation() -> None:
    payload = {
        "header": {
            "timbrado_number": "87654321",
            "establishment_code": "001",
            "point_of_issue_code": "001",
            "document_number": "0000012",
            "issue_date": "2026-10-14T12:00:00",
            "security_code": "123456789",
            "issuer_ruc": "80011111",
            "issuer_dv": "4",
            "issuer_legal_name": "Empresa General S.A.",
            "currency": "PYG",
        },
        "items": [
            {
                "line_number": 1,
                "description": "Licencia Enterprise",
                "quantity": 1,
                "unit_price": 25000000,
                "tax_rate": 10,
            }
        ],
        "profile": {
            "ruc": "80011111",
            "dv": "4",
            "legal_name": "Empresa General S.A.",
            "obligaciones": [OBLIGACION_IRE_GENERAL],
        },
        "simulation": True,
    }
    res = client.post("/api/v1/sifen/sign-and-send", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["status"] == "Aprobado"
    assert data["dCodRes"] == "0260"
    assert len(data["cdc"]) == 44
    assert "https://ekuatia.set.gov.py/consultas-test/qr?" in data["qr_url"]
    assert "rRetEnviDe" in data["raw_response"]
