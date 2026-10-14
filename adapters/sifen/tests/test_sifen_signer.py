"""
Unit tests for SIFEN digital signature and QR-code generation using pysifen.
"""

from datetime import datetime, timezone
from decimal import Decimal
import xml.etree.ElementTree as ET

from lxml import etree
from pysifen.enums import Ambiente
from pysifen.lectura import verificar_documento

from sifen.constants import OBLIGACION_IRE_GENERAL
from sifen.models import DteHeaderInput, DteItemInput, MandantRucProfile
from sifen.signer import SifenSigner, generate_mock_pkcs12
from sifen.xml_generator import SifenXmlGenerator


def test_mock_pkcs12_generation() -> None:
    p12_bytes, pwd = generate_mock_pkcs12(
        ruc="80011111", dv="4", legal_name="Comercio Grande S.A.", password="testpassword"
    )
    assert len(p12_bytes) > 500
    assert pwd == "testpassword"

    signer = SifenSigner(p12_bytes=p12_bytes, password=pwd, allow_mock=False)
    assert signer.firmante is not None


def test_signer_xml_signature_and_qr_integration() -> None:
    profile = MandantRucProfile(
        ruc="80011111",
        dv="4",
        legal_name="Comercio Grande S.A.",
        obligaciones=[OBLIGACION_IRE_GENERAL],
    )
    header = DteHeaderInput(
        timbrado_number="87654321",
        establishment_code="001",
        point_of_issue_code="001",
        document_number="0000002",
        issue_date=datetime(2026, 10, 14, 12, 0, 0),
        security_code="123456789",
        issuer_ruc="80011111",
        issuer_dv="4",
        issuer_legal_name="Comercio Grande S.A.",
        currency="PYG",
    )
    items = [
        DteItemInput(
            line_number=1,
            description="Servidor VibeCore Enterprise",
            quantity=Decimal(1),
            unit_price=Decimal(11000000),
            tax_rate=Decimal(10),
        )
    ]

    generator = SifenXmlGenerator()
    raw_xml = generator.generate_xml(header, items, profile)

    signer = SifenSigner(allow_mock=True)
    signed_xml, qr_url, cdc, digest_value = signer.sign_and_add_qr(
        raw_xml=raw_xml,
        csc="ABCD0000000000000000000000000000",
        id_csc="0001",
        ambiente="test",
        header=header,
    )

    assert cdc.startswith("01800111114")
    assert len(cdc) == 44
    assert digest_value is not None
    assert "https://ekuatia.set.gov.py/consultas-test/qr?" in qr_url
    assert f"Id={cdc}" in qr_url
    assert "cHashQR=" in qr_url

    # Check XML structure contains Signature and gCamFuFD
    root = etree.fromstring(signed_xml.encode("utf-8"))
    sig = root.find(".//{http://www.w3.org/2000/09/xmldsig#}Signature")
    assert sig is not None

    qr_elem = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dCarQR")
    assert qr_elem is not None
    assert qr_elem.text == qr_url

    # Verify signature cryptographically using pysifen
    verif = verificar_documento(signed_xml.encode("utf-8"), validar_esquema=False)
    assert verif.firma_valida is True
