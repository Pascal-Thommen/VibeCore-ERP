"""
Tests for isolated SIFEN Adapter module.
"""

import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal

from sifen.constants import (
    DTE_BOLETA_RESIMPLE,
    DTE_FACTURA_ELECTRONICA,
    OBLIGACION_IRE_GENERAL,
    OBLIGACION_IRE_RESIMPLE,
    TaxRegime,
)
from sifen.models import (
    DteHeaderInput,
    DteItemInput,
    MandantRucProfile,
)
from sifen.resolver import SifenProfileResolver
from sifen.xml_generator import SifenXmlGenerator


def test_adapter_resolver_and_generator_workflow() -> None:
    # 1. Test Resimple path
    resimple_profile = MandantRucProfile(
        ruc="80076543",
        dv="2",
        legal_name="Comercio Pequeno de Juan",
        obligaciones=[OBLIGACION_IRE_RESIMPLE],
    )
    resolved_resimple = SifenProfileResolver.resolve(resimple_profile)
    assert resolved_resimple.regime == TaxRegime.IRE_RESIMPLE
    assert resolved_resimple.dte_type == DTE_BOLETA_RESIMPLE
    assert resolved_resimple.iva_applicable is False

    header = DteHeaderInput(
        timbrado_number="87654321",
        establishment_code="001",
        point_of_issue_code="001",
        document_number="0000001",
        issue_date=datetime(2026, 10, 14, 12, 0, 0),
        security_code="123456789",
        issuer_ruc="80076543",
        issuer_dv="2",
        issuer_legal_name="Comercio Pequeno de Juan",
        currency="PYG",
    )
    items = [
        DteItemInput(
            line_number=1,
            description="Venta de Verduras Frescas",
            quantity=Decimal(5),
            unit_price=Decimal(10000),
            tax_rate=Decimal(10),  # Ignored for Resimple
        )
    ]

    generator = SifenXmlGenerator()
    xml_resimple = generator.generate_xml(header, items, resolved_resimple)
    root = ET.fromstring(xml_resimple)
    assert root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}iTiDE").text == "4"
    assert root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}iAfecIVA").text == "3"
    assert root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dTotIVA").text == "0"
    assert root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dTotOpe").text == "50000"

    # 2. Test Factura Electrónica path
    general_profile = MandantRucProfile(
        ruc="80011111",
        dv="4",
        legal_name="Comercio Grande S.A.",
        obligaciones=[OBLIGACION_IRE_GENERAL],
    )
    resolved_general = SifenProfileResolver.resolve(general_profile)
    assert resolved_general.regime == TaxRegime.IRE_GENERAL
    assert resolved_general.dte_type == DTE_FACTURA_ELECTRONICA
    assert resolved_general.iva_applicable is True

    header_fe = DteHeaderInput(
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
    items_fe = [
        DteItemInput(
            line_number=1,
            description="Servidor VibeCore Enterprise",
            quantity=Decimal(1),
            unit_price=Decimal(11000000),
            tax_rate=Decimal(10),
        )
    ]
    xml_fe = generator.generate_xml(header_fe, items_fe, resolved_general)
    root_fe = ET.fromstring(xml_fe)
    assert root_fe.find(".//{http://ekuatia.set.gov.py/sifen/xsd}iTiDE").text == "1"
    assert root_fe.find(".//{http://ekuatia.set.gov.py/sifen/xsd}iAfecIVA").text == "1"
    assert (
        root_fe.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dLiqIVAItem").text
        == "1000000"
    )
    assert (
        root_fe.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dTotIVA").text
        == "1000000"
    )
