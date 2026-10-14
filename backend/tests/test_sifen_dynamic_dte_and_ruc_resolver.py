"""
Unit tests for SIFEN Dynamic DTE Generator and Automatic RUC Profile Resolver.

Tests:
1. Mandant RUC profile resolution (IRE 700 General, 701 Simple, 702 Resimple).
2. DTE type steering: Factura Electrónica (iTiDE = 1) vs Boleta Resimple Electrónica (iTiDE = 4).
3. Tax calculation: Full IVA (10%, 5%, Exento) vs Resimple (Gross only, no IVA).
4. SIFEN CDC generation with official Modulo 11 algorithm.
5. SIFEN XML generation and schema structure for both DTE types.
"""

import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal

import pytest

from app.sifen.constants import (
    DTE_BOLETA_RESIMPLE,
    DTE_FACTURA_ELECTRONICA,
    IVA_AFECTACION_EXENTO,
    IVA_AFECTACION_GRAVADO,
    OBLIGACION_IRE_GENERAL,
    OBLIGACION_IRE_RESIMPLE,
    OBLIGACION_IRE_SIMPLE,
    TaxRegime,
)
from app.sifen.models import (
    DteHeaderInput,
    DteItemInput,
    MandantObligacion,
    MandantRucProfile,
    ResolvedProfile,
)
from app.sifen.resolver import SifenProfileResolver
from app.sifen.xml_generator import (
    SifenXmlGenerator,
    compute_sifen_modulo_11,
    generate_sifen_cdc,
)


def sample_header(issuer_ruc: str = "80012345", issuer_dv: str = "6") -> DteHeaderInput:
    """Helper to build a valid DteHeaderInput."""
    return DteHeaderInput(
        timbrado_number="12548963",
        establishment_code="001",
        point_of_issue_code="001",
        document_number="0000042",
        issue_date=datetime(2026, 10, 14, 10, 30, 0),
        security_code="987654321",
        emission_type=1,
        contributor_type=2,
        issuer_ruc=issuer_ruc,
        issuer_dv=issuer_dv,
        issuer_legal_name="VibeCore Paraguay S.A.",
        issuer_trade_name="VibeCore ERP",
        receiver_ruc="80099999",
        receiver_dv="1",
        receiver_legal_name="Cliente de Prueba S.A.",
        currency="PYG",
    )


class TestRucProfileResolver:
    """Tests for Step 1 & 2: RUC profile recognition and tax steering."""

    def test_resolve_ire_general_code_700(self) -> None:
        profile = MandantRucProfile(
            ruc="80012345",
            dv="6",
            legal_name="Empresa General S.A.",
            obligaciones=[OBLIGACION_IRE_GENERAL, 211],
        )
        resolved = SifenProfileResolver.resolve(profile)

        assert resolved.regime == TaxRegime.IRE_GENERAL
        assert resolved.obligation_code == 700
        assert resolved.dte_type == DTE_FACTURA_ELECTRONICA
        assert resolved.dte_type_code == "01"
        assert resolved.dte_type_description == "Factura electrónica"
        assert resolved.iva_applicable is True
        assert resolved.requires_iva_breakdown is True

    def test_resolve_ire_simple_code_701(self) -> None:
        profile = MandantRucProfile(
            ruc="80023456",
            dv="7",
            legal_name="Empresa Simple S.R.L.",
            obligaciones=[MandantObligacion(code=OBLIGACION_IRE_SIMPLE, description="IRE SIMPLE")],
        )
        resolved = SifenProfileResolver.resolve(profile)

        assert resolved.regime == TaxRegime.IRE_SIMPLE
        assert resolved.obligation_code == 701
        assert resolved.dte_type == DTE_FACTURA_ELECTRONICA
        assert resolved.dte_type_code == "01"
        assert resolved.dte_type_description == "Factura electrónica"
        assert resolved.iva_applicable is True
        assert resolved.requires_iva_breakdown is True

    def test_resolve_ire_resimple_code_702(self) -> None:
        profile = MandantRucProfile(
            ruc="80034567",
            dv="8",
            legal_name="Pyme Resimple de Juan Perez",
            obligaciones=[OBLIGACION_IRE_RESIMPLE],
        )
        resolved = SifenProfileResolver.resolve(profile)

        assert resolved.regime == TaxRegime.IRE_RESIMPLE
        assert resolved.obligation_code == 702
        assert resolved.dte_type == DTE_BOLETA_RESIMPLE
        assert resolved.dte_type_code == "04"
        assert resolved.dte_type_description == "Boleta resimple electrónica"
        assert resolved.iva_applicable is False
        assert resolved.requires_iva_breakdown is False

    def test_resolve_from_raw_dictionary_or_list(self) -> None:
        resolved_dict = SifenProfileResolver.resolve({"obligaciones": [700, 211]})
        assert resolved_dict.regime == TaxRegime.IRE_GENERAL

        resolved_list = SifenProfileResolver.resolve([702])
        assert resolved_list.regime == TaxRegime.IRE_RESIMPLE

    def test_resolve_missing_ire_obligation_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Keine gueltige IRE-Steuerpflicht"):
            SifenProfileResolver.resolve({"obligaciones": [211, 999]})

    def test_resolve_invalid_format_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="Ungueltiges RUC-Profilformat"):
            SifenProfileResolver.resolve("invalid-profile-format")  # type: ignore


class TestTaxCalculation:
    """Tests for item-level tax calculation across tax regimes."""

    def test_ire_general_iva_10_percent_pyg(self) -> None:
        resolved = ResolvedProfile.from_regime(TaxRegime.IRE_GENERAL, 700)
        # 110,000 PYG gross item
        tax = SifenProfileResolver.calculate_item_tax(
            resolved=resolved,
            quantity=Decimal("1"),
            unit_price=Decimal("110000"),
            tax_rate=Decimal("10"),
            currency="PYG",
        )

        assert tax.afectacion_iva == IVA_AFECTACION_GRAVADO
        assert tax.tasa_iva == Decimal("10")
        assert tax.proporcion_iva == Decimal("100")
        assert tax.base_gravada == Decimal("100000")
        assert tax.liquidacion_iva == Decimal("10000")
        assert tax.total_item == Decimal("110000")

    def test_ire_general_iva_5_percent_pyg(self) -> None:
        resolved = ResolvedProfile.from_regime(TaxRegime.IRE_GENERAL, 700)
        # 105,000 PYG gross item
        tax = SifenProfileResolver.calculate_item_tax(
            resolved=resolved,
            quantity=Decimal("1"),
            unit_price=Decimal("105000"),
            tax_rate=Decimal("5"),
            currency="PYG",
        )

        assert tax.afectacion_iva == IVA_AFECTACION_GRAVADO
        assert tax.tasa_iva == Decimal("5")
        assert tax.proporcion_iva == Decimal("100")
        assert tax.base_gravada == Decimal("100000")
        assert tax.liquidacion_iva == Decimal("5000")
        assert tax.total_item == Decimal("105000")

    def test_ire_general_exento(self) -> None:
        resolved = ResolvedProfile.from_regime(TaxRegime.IRE_GENERAL, 700)
        tax = SifenProfileResolver.calculate_item_tax(
            resolved=resolved,
            quantity=Decimal("2"),
            unit_price=Decimal("50000"),
            tax_rate=Decimal("0"),
            currency="PYG",
        )

        assert tax.afectacion_iva == IVA_AFECTACION_EXENTO
        assert tax.tasa_iva == Decimal("0")
        assert tax.base_gravada == Decimal("0")
        assert tax.liquidacion_iva == Decimal("0")
        assert tax.total_item == Decimal("100000")

    def test_ire_resimple_no_iva_calculation_gross_only(self) -> None:
        resolved = ResolvedProfile.from_regime(TaxRegime.IRE_RESIMPLE, 702)
        # Even if input had tax_rate=10, Resimple mandates no IVA and only gross amount
        tax = SifenProfileResolver.calculate_item_tax(
            resolved=resolved,
            quantity=Decimal("3"),
            unit_price=Decimal("45000"),
            tax_rate=Decimal("10"),
            currency="PYG",
        )

        assert tax.afectacion_iva == IVA_AFECTACION_EXENTO
        assert tax.tasa_iva == Decimal("0")
        assert tax.proporcion_iva == Decimal("0")
        assert tax.base_gravada == Decimal("0")
        assert tax.liquidacion_iva == Decimal("0")
        assert tax.total_item == Decimal("135000")

    def test_unsupported_tax_rate_raises_error(self) -> None:
        resolved = ResolvedProfile.from_regime(TaxRegime.IRE_GENERAL, 700)
        with pytest.raises(ValueError, match="Nicht unterstuetzter IVA-Steuersatz"):
            SifenProfileResolver.calculate_item_tax(
                resolved=resolved,
                quantity=Decimal("1"),
                unit_price=Decimal("1000"),
                tax_rate=Decimal("19"),
            )


class TestSifenCdcGeneration:
    """Tests for SIFEN CDC generation and Modulo 11 check digit."""

    def test_compute_modulo_11(self) -> None:
        # Test vector for Modulo 11 with base 11
        # Example 43-digit base CDC
        base_43 = "0180012345600100100000422202610141987654321"
        assert len(base_43) == 43
        dv = compute_sifen_modulo_11(base_43, base_max=11)
        assert 0 <= dv <= 9

    def test_generate_sifen_cdc(self) -> None:
        header = sample_header()
        cdc, dv = generate_sifen_cdc(header, dte_type=1)

        assert len(cdc) == 44
        assert cdc.isdigit()
        assert cdc.startswith("01")  # iTiDE = 1 -> "01"
        assert cdc.endswith(dv)

        # For Boleta Resimple (dte_type=4)
        cdc_resimple, dv_resimple = generate_sifen_cdc(header, dte_type=4)
        assert len(cdc_resimple) == 44
        assert cdc_resimple.startswith("04")  # iTiDE = 4 -> "04"
        assert cdc_resimple.endswith(dv_resimple)


class TestSifenXmlGenerator:
    """Tests for Step 2: XML generator logic for Factura Electrónica and Boleta Resimple."""

    def test_generate_factura_electronica_xml_ire_general(self) -> None:
        generator = SifenXmlGenerator()
        header = sample_header()
        items = [
            DteItemInput(
                line_number=1,
                code="SERV-001",
                description="Consultoria ERP Cloud",
                quantity=Decimal("1"),
                unit_price=Decimal("1100000"),
                tax_rate=Decimal("10"),
            ),
            DteItemInput(
                line_number=2,
                code="PROD-002",
                description="Libro Guia SIFEN",
                quantity=Decimal("2"),
                unit_price=Decimal("52500"),
                tax_rate=Decimal("5"),
            ),
        ]
        profile = MandantRucProfile(
            ruc="80012345",
            dv="6",
            legal_name="VibeCore Paraguay S.A.",
            obligaciones=[OBLIGACION_IRE_GENERAL],
        )

        xml_str = generator.generate_xml(header, items, profile)

        # XML Parsing verification
        root = ET.fromstring(xml_str)
        assert root.tag.endswith("rDE")

        # Check DE Id matches CDC
        de = root.find("{http://ekuatia.set.gov.py/sifen/xsd}DE")
        assert de is not None
        cdc_id = de.attrib.get("Id")
        assert cdc_id is not None
        assert len(cdc_id) == 44
        assert cdc_id.startswith("01")

        # Check iTiDE = 1 and Description
        g_timb = de.find("{http://ekuatia.set.gov.py/sifen/xsd}gTimb")
        assert g_timb is not None
        assert g_timb.findtext("{http://ekuatia.set.gov.py/sifen/xsd}iTiDE") == "1"
        assert (
            g_timb.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dDesTiDE")
            == "Factura electrónica"
        )

        # Check gCamFE is present for Factura Electrónica
        g_dtip_de = de.find("{http://ekuatia.set.gov.py/sifen/xsd}gDtipDE")
        assert g_dtip_de is not None
        assert g_dtip_de.find("{http://ekuatia.set.gov.py/sifen/xsd}gCamFE") is not None

        # Check item gCamIVA values
        item_nodes = g_dtip_de.findall("{http://ekuatia.set.gov.py/sifen/xsd}gCamItem")
        assert len(item_nodes) == 2

        # Item 1: IVA 10%
        cam_iva_1 = item_nodes[0].find("{http://ekuatia.set.gov.py/sifen/xsd}gCamIVA")
        assert cam_iva_1 is not None
        assert cam_iva_1.findtext("{http://ekuatia.set.gov.py/sifen/xsd}iAfecIVA") == "1"
        assert cam_iva_1.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dTasaIVA") == "10"
        assert cam_iva_1.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dBasGravIVA") == "1000000"
        assert cam_iva_1.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dLiqIVAItem") == "100000"

        # Item 2: IVA 5% (total = 105,000)
        cam_iva_2 = item_nodes[1].find("{http://ekuatia.set.gov.py/sifen/xsd}gCamIVA")
        assert cam_iva_2 is not None
        assert cam_iva_2.findtext("{http://ekuatia.set.gov.py/sifen/xsd}iAfecIVA") == "1"
        assert cam_iva_2.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dTasaIVA") == "5"
        assert cam_iva_2.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dBasGravIVA") == "100000"
        assert cam_iva_2.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dLiqIVAItem") == "5000"

        # Check Totals gTotSub
        g_tot_sub = de.find("{http://ekuatia.set.gov.py/sifen/xsd}gTotSub")
        assert g_tot_sub is not None
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dSub10") == "1100000"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dSub5") == "105000"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dTotOpe") == "1205000"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dIVA10") == "100000"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dIVA5") == "5000"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dTotIVA") == "105000"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dBaseGrav10") == "1000000"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dBaseGrav5") == "100000"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dTotBasGrav") == "1100000"

    def test_generate_boleta_resimple_xml_ire_resimple(self) -> None:
        generator = SifenXmlGenerator()
        header = sample_header(issuer_ruc="80034567", issuer_dv="8")
        items = [
            DteItemInput(
                line_number=1,
                code="ART-01",
                description="Servicio de Reparacion Basica",
                quantity=Decimal("1"),
                unit_price=Decimal("150000"),
                tax_rate=Decimal("10"),  # Should be bypassed by Resimple
            ),
            DteItemInput(
                line_number=2,
                code="ART-02",
                description="Repuesto Artesanal",
                quantity=Decimal("2"),
                unit_price=Decimal("25000"),
                tax_rate=Decimal("0"),
            ),
        ]
        profile = MandantRucProfile(
            ruc="80034567",
            dv="8",
            legal_name="Taller Resimple de Juan Gomez",
            obligaciones=[OBLIGACION_IRE_RESIMPLE],
        )

        xml_str = generator.generate_xml(header, items, profile)

        # XML Parsing verification
        root = ET.fromstring(xml_str)
        de = root.find("{http://ekuatia.set.gov.py/sifen/xsd}DE")
        assert de is not None
        cdc_id = de.attrib.get("Id")
        assert cdc_id is not None
        assert len(cdc_id) == 44
        assert cdc_id.startswith("04")  # Boleta Resimple is 04

        # Check iTiDE = 4 and Description
        g_timb = de.find("{http://ekuatia.set.gov.py/sifen/xsd}gTimb")
        assert g_timb is not None
        assert g_timb.findtext("{http://ekuatia.set.gov.py/sifen/xsd}iTiDE") == "4"
        assert (
            g_timb.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dDesTiDE")
            == "Boleta resimple electrónica"
        )

        # Check gCamFE is NOT present for Boleta Resimple
        g_dtip_de = de.find("{http://ekuatia.set.gov.py/sifen/xsd}gDtipDE")
        assert g_dtip_de is not None
        assert g_dtip_de.find("{http://ekuatia.set.gov.py/sifen/xsd}gCamFE") is None

        # Check items: Steuerberechnung: Keine IVA
        # (steuerbefreit markiert, keine IVA-Berechnung, nur Bruttoendbetrag)
        item_nodes = g_dtip_de.findall("{http://ekuatia.set.gov.py/sifen/xsd}gCamItem")
        assert len(item_nodes) == 2

        for item_node in item_nodes:
            cam_iva = item_node.find("{http://ekuatia.set.gov.py/sifen/xsd}gCamIVA")
            assert cam_iva is not None
            assert (
                cam_iva.findtext("{http://ekuatia.set.gov.py/sifen/xsd}iAfecIVA") == "3"
            )  # Exento
            assert cam_iva.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dDesAfecIVA") == "Exento"
            assert cam_iva.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dPropIVA") == "0"
            assert cam_iva.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dTasaIVA") == "0"
            assert cam_iva.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dBasGravIVA") == "0"
            assert cam_iva.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dLiqIVAItem") == "0"

        # Check Totals gTotSub: No IVA breakdown, only gross amount (total 200,000)
        g_tot_sub = de.find("{http://ekuatia.set.gov.py/sifen/xsd}gTotSub")
        assert g_tot_sub is not None
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dSubExe") == "200000"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dSub10") == "0"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dSub5") == "0"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dTotOpe") == "200000"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dTotGralOpe") == "200000"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dIVA10") == "0"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dIVA5") == "0"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dTotIVA") == "0"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dBaseGrav10") == "0"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dBaseGrav5") == "0"
        assert g_tot_sub.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dTotBasGrav") == "0"
