"""
SIFEN DTE XML Generator for Factura Electrónica and Boleta Resimple Electrónica.
Complies with Paraguayan DNIT / SET SIFEN Technical Manual Version 150.
"""

import xml.etree.ElementTree as ET
from decimal import Decimal
from xml.dom import minidom

from app.sifen.constants import (
    DTE_BOLETA_RESIMPLE,
    DTE_FACTURA_ELECTRONICA,
    DTE_TYPE_CODES,
    SIFEN_FORMAT_VERSION,
    SIFEN_XML_NAMESPACE,
)
from app.sifen.models import (
    DteHeaderInput,
    DteItemInput,
    ItemTaxDetail,
    MandantRucProfile,
    ResolvedProfile,
)
from app.sifen.resolver import SifenProfileResolver


def compute_sifen_modulo_11(number_str: str, base_max: int = 11) -> int:
    """
    Compute Check Digit (DV) for CDC and RUC using official SIFEN Modulo 11 algorithm.

    Formula (SET / DNIT):
    - Weight sequence from right to left starts at 2, increments to base_max, then wraps to 2.
    - Sum = sum(digit * weight)
    - Remainder = Sum % 11
    - If Remainder > 1 -> DV = 11 - Remainder, else DV = 0.
    """
    total = 0
    k = 2
    for char in reversed(number_str):
        if not char.isdigit():
            # If letters exist, substitute ord(char.upper())
            for sub_char in reversed(str(ord(char.upper()))):
                if k > base_max:
                    k = 2
                total += int(sub_char) * k
                k += 1
        else:
            if k > base_max:
                k = 2
            total += int(char) * k
            k += 1

    remainder = total % 11
    return 11 - remainder if remainder > 1 else 0


def generate_sifen_cdc(header: DteHeaderInput, dte_type: int) -> tuple[str, str]:
    """
    Generate 44-digit SIFEN CDC (Código de Control) and its DV.

    CDC composition (43 digits + 1 DV = 44 digits):
    - iTiDE (2 digits)
    - dRucEm (8 digits, zero-padded)
    - dDVEmi (1 digit)
    - dEst (3 digits)
    - dPunExp (3 digits)
    - dNumDoc (7 digits)
    - iTipCont (1 digit)
    - dFeEmiDE (8 digits, YYYYMMDD)
    - iTipEmi (1 digit)
    - dCodSeg (9 digits)
    - DV (1 digit via Modulo 11)
    """
    ti_de_str = DTE_TYPE_CODES.get(dte_type, f"{dte_type:02d}")
    ruc_padded = header.issuer_ruc.zfill(8)
    dv_emi = header.issuer_dv
    est = header.establishment_code.zfill(3)
    pun_exp = header.point_of_issue_code.zfill(3)
    num_doc = header.document_number.zfill(7)
    tip_cont = str(header.contributor_type)
    fe_emi = header.issue_date.strftime("%Y%m%d")
    tip_emi = str(header.emission_type)
    cod_seg = header.security_code.zfill(9)

    base_43 = (
        f"{ti_de_str}{ruc_padded}{dv_emi}{est}{pun_exp}"
        f"{num_doc}{tip_cont}{fe_emi}{tip_emi}{cod_seg}"
    )
    if len(base_43) != 43:
        raise ValueError(f"Base CDC must be exactly 43 digits, got {len(base_43)}: {base_43}")

    dv = compute_sifen_modulo_11(base_43, base_max=11)
    cdc = f"{base_43}{dv}"
    return cdc, str(dv)


class SifenXmlGenerator:
    """Generates official SIFEN XML for Factura Electrónica and Boleta Resimple Electrónica."""

    def __init__(self, resolver: SifenProfileResolver | None = None) -> None:
        self.resolver = resolver or SifenProfileResolver()

    def generate_xml(
        self,
        header: DteHeaderInput,
        items: list[DteItemInput],
        profile_or_resolved: MandantRucProfile | ResolvedProfile | dict,
        pretty: bool = True,
    ) -> str:
        """
        Generate complete SIFEN DTE XML according to the Mandant's resolved profile.

        - For Factura Electrónica (iTiDE = 1): Includes gCamFE, gCamIVA, and VAT subtotals.
        - For Boleta Resimple Electrónica (iTiDE = 4): No VAT liquidation, gross amounts only.
        """
        if not items:
            raise ValueError("Document items list cannot be empty for SIFEN DTE generation")

        if isinstance(profile_or_resolved, ResolvedProfile):
            resolved = profile_or_resolved
        else:
            resolved = self.resolver.resolve(profile_or_resolved)

        cdc, cdc_dv = generate_sifen_cdc(header, resolved.dte_type)

        # Root element
        rde = ET.Element("rDE", {"xmlns": SIFEN_XML_NAMESPACE})
        ET.SubElement(rde, "dDVId").text = cdc_dv

        de = ET.SubElement(rde, "DE", {"Id": cdc})
        ET.SubElement(de, "dVerFor").text = SIFEN_FORMAT_VERSION

        # gOpeDE
        g_ope_de = ET.SubElement(de, "gOpeDE")
        ET.SubElement(g_ope_de, "iTipEmi").text = str(header.emission_type)
        ET.SubElement(g_ope_de, "dDesTipEmi").text = (
            "Normal" if header.emission_type == 1 else "Contingencia"
        )
        ET.SubElement(g_ope_de, "dCodSeg").text = header.security_code.zfill(9)

        # gTimb
        g_timb = ET.SubElement(de, "gTimb")
        ET.SubElement(g_timb, "iTiDE").text = str(resolved.dte_type)
        ET.SubElement(g_timb, "dDesTiDE").text = resolved.dte_type_description
        ET.SubElement(g_timb, "dNumTim").text = header.timbrado_number
        ET.SubElement(g_timb, "dEst").text = header.establishment_code.zfill(3)
        ET.SubElement(g_timb, "dPunExp").text = header.point_of_issue_code.zfill(3)
        ET.SubElement(g_timb, "dNumDoc").text = header.document_number.zfill(7)
        ET.SubElement(g_timb, "dFeIniT").text = header.issue_date.strftime("%Y-%m-%d")

        # gDatGralOpe
        g_dat_gral_ope = ET.SubElement(de, "gDatGralOpe")
        ET.SubElement(g_dat_gral_ope, "dFeEmiDE").text = header.issue_date.strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        # gEmis
        g_emis = ET.SubElement(g_dat_gral_ope, "gEmis")
        ET.SubElement(g_emis, "dRucEm").text = header.issuer_ruc.zfill(8)
        ET.SubElement(g_emis, "dDVEmi").text = header.issuer_dv
        ET.SubElement(g_emis, "iTipCont").text = str(header.contributor_type)
        ET.SubElement(g_emis, "dNomEmi").text = header.issuer_legal_name
        if header.issuer_trade_name:
            ET.SubElement(g_emis, "dNomFanEmi").text = header.issuer_trade_name
        ET.SubElement(g_emis, "dDirEmi").text = header.issuer_address
        ET.SubElement(g_emis, "dNumCas").text = "0"
        ET.SubElement(g_emis, "cDepEmi").text = header.issuer_department_code
        ET.SubElement(g_emis, "dDesDepEmi").text = "Capital"
        ET.SubElement(g_emis, "cDisEmi").text = header.issuer_district_code
        ET.SubElement(g_emis, "dDesDisEmi").text = "Asuncion"
        ET.SubElement(g_emis, "cCiuEmi").text = header.issuer_city_code
        ET.SubElement(g_emis, "dDesCiuEmi").text = header.issuer_city

        g_act_eco = ET.SubElement(g_emis, "gActEco")
        ET.SubElement(g_act_eco, "cActEco").text = header.issuer_economic_activity_code
        ET.SubElement(g_act_eco, "dDesActEco").text = header.issuer_economic_activity_desc

        # gDatRec
        g_dat_rec = ET.SubElement(g_dat_gral_ope, "gDatRec")
        ET.SubElement(g_dat_rec, "iNatRec").text = str(header.receiver_nature)
        ET.SubElement(g_dat_rec, "iTiOpe").text = str(header.operation_type)
        ET.SubElement(g_dat_rec, "cPaisRec").text = "PRY"
        ET.SubElement(g_dat_rec, "dDesPaisRe").text = "Paraguay"

        if header.receiver_ruc and header.receiver_dv:
            ET.SubElement(g_dat_rec, "iTiContRec").text = "2"
            ET.SubElement(g_dat_rec, "dRucRec").text = header.receiver_ruc
            ET.SubElement(g_dat_rec, "dDVRec").text = header.receiver_dv
        elif header.receiver_doc_number:
            ET.SubElement(g_dat_rec, "iTipIDRec").text = str(header.receiver_doc_type or 1)
            ET.SubElement(g_dat_rec, "dNumIDRec").text = header.receiver_doc_number

        ET.SubElement(g_dat_rec, "dNomRec").text = header.receiver_legal_name

        # gDtipDE
        g_dtip_de = ET.SubElement(de, "gDtipDE")

        # Specific fields for Factura Electrónica (iTiDE = 1)
        if resolved.dte_type == DTE_FACTURA_ELECTRONICA:
            g_cam_fe = ET.SubElement(g_dtip_de, "gCamFE")
            ET.SubElement(g_cam_fe, "iIndPres").text = "1"
            ET.SubElement(g_cam_fe, "dDesIndPres").text = "Operacion presencial"

        # Item processing and subtotal accumulators
        sub_10 = Decimal("0")
        sub_5 = Decimal("0")
        sub_exe = Decimal("0")
        total_ope = Decimal("0")
        iva_10 = Decimal("0")
        iva_5 = Decimal("0")
        base_10 = Decimal("0")
        base_5 = Decimal("0")

        for item in items:
            tax_detail: ItemTaxDetail = self.resolver.calculate_item_tax(
                resolved=resolved,
                quantity=item.quantity,
                unit_price=item.unit_price,
                discount=item.discount,
                tax_rate=item.tax_rate,
                currency=header.currency,
            )

            total_ope += tax_detail.total_item

            if resolved.dte_type == DTE_BOLETA_RESIMPLE:
                # Boleta Resimple: All operations recorded as exempt / non-taxed gross
                sub_exe += tax_detail.total_item
            else:
                # Factura Electrónica: Categorize by tax rate
                if item.tax_rate == Decimal("10"):
                    sub_10 += tax_detail.total_item
                    iva_10 += tax_detail.liquidacion_iva
                    base_10 += tax_detail.base_gravada
                elif item.tax_rate == Decimal("5"):
                    sub_5 += tax_detail.total_item
                    iva_5 += tax_detail.liquidacion_iva
                    base_5 += tax_detail.base_gravada
                else:
                    sub_exe += tax_detail.total_item

            # gCamItem
            g_cam_item = ET.SubElement(g_dtip_de, "gCamItem")
            ET.SubElement(g_cam_item, "dCodInt").text = item.code or str(item.line_number)
            ET.SubElement(g_cam_item, "dDesProSer").text = item.description
            ET.SubElement(g_cam_item, "cUniMed").text = item.unit_of_measure
            ET.SubElement(g_cam_item, "dCantProSer").text = str(item.quantity)

            # gValorItem
            g_valor_item = ET.SubElement(g_cam_item, "gValorItem")
            ET.SubElement(g_valor_item, "dPUniProSer").text = str(item.unit_price)
            gross_item = item.quantity * item.unit_price
            ET.SubElement(g_valor_item, "dTotBruOpeItem").text = str(gross_item)

            # gValorRestaItem
            g_valor_resta = ET.SubElement(g_valor_item, "gValorRestaItem")
            if item.discount > Decimal("0"):
                ET.SubElement(g_valor_resta, "dDescItem").text = str(item.discount)
            ET.SubElement(g_valor_resta, "dTotOpeItem").text = str(tax_detail.total_item)

            # gCamIVA
            # SIFEN requirement:
            # Factura Electrónica: displays gCamIVA with breakdown (dBasGravIVA, dLiqIVAItem)
            # Boleta Resimple: marked exempt, no IVA calculation, only gross amount
            g_cam_iva = ET.SubElement(g_cam_item, "gCamIVA")
            ET.SubElement(g_cam_iva, "iAfecIVA").text = str(tax_detail.afectacion_iva)
            ET.SubElement(g_cam_iva, "dDesAfecIVA").text = tax_detail.des_afectacion_iva
            ET.SubElement(g_cam_iva, "dPropIVA").text = str(tax_detail.proporcion_iva)
            ET.SubElement(g_cam_iva, "dTasaIVA").text = str(tax_detail.tasa_iva)
            ET.SubElement(g_cam_iva, "dBasGravIVA").text = str(tax_detail.base_gravada)
            ET.SubElement(g_cam_iva, "dLiqIVAItem").text = str(tax_detail.liquidacion_iva)

        # gTotSub (Totals section)
        g_tot_sub = ET.SubElement(de, "gTotSub")
        ET.SubElement(g_tot_sub, "dSubExe").text = str(sub_exe)
        ET.SubElement(g_tot_sub, "dSub5").text = str(sub_5)
        ET.SubElement(g_tot_sub, "dSub10").text = str(sub_10)
        ET.SubElement(g_tot_sub, "dTotOpe").text = str(total_ope)
        ET.SubElement(g_tot_sub, "dTotGralOpe").text = str(total_ope)

        if resolved.dte_type == DTE_FACTURA_ELECTRONICA:
            ET.SubElement(g_tot_sub, "dIVA5").text = str(iva_5)
            ET.SubElement(g_tot_sub, "dIVA10").text = str(iva_10)
            ET.SubElement(g_tot_sub, "dTotIVA").text = str(iva_10 + iva_5)
            ET.SubElement(g_tot_sub, "dBaseGrav5").text = str(base_5)
            ET.SubElement(g_tot_sub, "dBaseGrav10").text = str(base_10)
            ET.SubElement(g_tot_sub, "dTotBasGrav").text = str(base_10 + base_5)
        else:
            # Boleta Resimple: No IVA breakdown, all zero
            ET.SubElement(g_tot_sub, "dIVA5").text = "0"
            ET.SubElement(g_tot_sub, "dIVA10").text = "0"
            ET.SubElement(g_tot_sub, "dTotIVA").text = "0"
            ET.SubElement(g_tot_sub, "dBaseGrav5").text = "0"
            ET.SubElement(g_tot_sub, "dBaseGrav10").text = "0"
            ET.SubElement(g_tot_sub, "dTotBasGrav").text = "0"

        xml_raw = ET.tostring(rde, encoding="utf-8")
        if pretty:
            parsed = minidom.parseString(xml_raw)
            return parsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")

        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_raw.decode("utf-8")}'
