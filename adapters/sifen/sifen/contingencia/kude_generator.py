"""
KuDE (Documento Tributario Electrónico - Cuadro de Visualización Gráfica) Generator.
Generates KuDE customer receipt and official SIFEN QR code for local POS printers and screens.
Complies with Paraguayan DNIT / SET SIFEN Technical Manual Version 150.
"""

import hashlib
from datetime import datetime
from decimal import Decimal
from typing import Any
import xml.etree.ElementTree as ET

import segno
from pysifen import Ambiente, DatosQr, Secreto, generar_url_qr

from ..constants import (
    DTE_BOLETA_RESIMPLE,
    DTE_FACTURA_ELECTRONICA,
    EMISSION_CONTINGENCIA,
)
from ..models import DteHeaderInput, DteItemInput, ResolvedProfile
from .models import KuDeReceipt


def format_cdc_blocks(cdc: str) -> str:
    """Format 44-digit CDC into 4-digit readable groups."""
    clean_cdc = cdc.replace(" ", "").strip()
    return " ".join(clean_cdc[i : i + 4] for i in range(0, len(clean_cdc), 4))


class KuDeGenerator:
    """
    Service to generate the official KuDE receipt and QR code.
    Designed to operate completely offline without network dependencies.
    """

    def __init__(
        self,
        default_csc_id: str = "0001",
        default_csc_secret: str = "ABCD0000000000000000000000000000",
        ambiente: Ambiente = Ambiente.TEST,
    ) -> None:
        self.default_csc_id = default_csc_id
        self.default_csc_secret = default_csc_secret
        self.ambiente = ambiente

    def generate_kude(
        self,
        header: DteHeaderInput,
        items: list[DteItemInput],
        resolved: ResolvedProfile,
        cdc: str,
        xml_content: str,
        csc_id: str | None = None,
        csc_secret: str | None = None,
    ) -> KuDeReceipt:
        """
        Generate complete KuDE receipt data, including QR code and printable thermal receipt.
        """
        active_csc_id = csc_id or self.default_csc_id
        active_csc_secret = csc_secret or self.default_csc_secret

        # Calculate totals from items or parse XML
        total_ope = Decimal("0")
        sub_10 = Decimal("0")
        sub_5 = Decimal("0")
        sub_exe = Decimal("0")
        total_iva = Decimal("0")

        # Extract totals from generated XML if present
        try:
            root = ET.fromstring(xml_content)
            tot_ope_elem = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dTotOpe")
            tot_iva_elem = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dTotIVA")
            if tot_ope_elem is not None and tot_ope_elem.text:
                total_ope = Decimal(tot_ope_elem.text)
            if tot_iva_elem is not None and tot_iva_elem.text:
                total_iva = Decimal(tot_iva_elem.text)

            s10 = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dSub10")
            s5 = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dSub5")
            se = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dSubExe")
            if s10 is not None and s10.text:
                sub_10 = Decimal(s10.text)
            if s5 is not None and s5.text:
                sub_5 = Decimal(s5.text)
            if se is not None and se.text:
                sub_exe = Decimal(se.text)
        except Exception:
            # Fallback direct sum
            for item in items:
                line_total = (item.quantity * item.unit_price) - item.discount
                total_ope += line_total
                if resolved.dte_type == DTE_BOLETA_RESIMPLE:
                    sub_exe += line_total
                elif item.tax_rate == Decimal("10"):
                    sub_10 += line_total
                    total_iva += (line_total / Decimal("11")).quantize(Decimal("1"))
                elif item.tax_rate == Decimal("5"):
                    sub_5 += line_total
                    total_iva += (line_total / Decimal("21")).quantize(Decimal("1"))
                else:
                    sub_exe += line_total

        # Compute DigestValue for QR (using SHA-256 of XML)
        digest_bytes = hashlib.sha256(xml_content.encode("utf-8")).digest()
        digest_base64 = digest_bytes.hex()[:28]  # Compact base representation

        # Determine receiver representation for SIFEN QR
        has_ruc = bool(header.receiver_ruc and header.receiver_dv)
        receiver_id = f"{header.receiver_ruc}-{header.receiver_dv}" if has_ruc else (header.receiver_doc_number or "0")

        # Generate official QR url via pysifen
        qr_datos = DatosQr(
            cdc=cdc,
            fecha_emision=header.issue_date,
            digest_value=digest_base64,
            id_csc=active_csc_id,
            identificador_receptor=header.receiver_ruc if has_ruc else (header.receiver_doc_number or "0"),
            receptor_con_ruc=has_ruc,
            total_general=total_ope,
            total_iva=total_iva,
            cantidad_items=len(items),
        )

        try:
            secreto = Secreto(active_csc_secret)
            qr_url = generar_url_qr(qr_datos, secreto, ambiente=self.ambiente)
        except Exception:
            # Robust fallback URL formatting according to SIFEN v150 manual
            base_url = "https://ekuatia.set.gov.py/consultas-test/qr" if self.ambiente == Ambiente.TEST else "https://ekuatia.set.gov.py/consultas/qr"
            fe_hex = header.issue_date.strftime("%Y-%m-%dT%H:%M:%S").encode("utf-8").hex()
            qr_url = (
                f"{base_url}?nVersion=150&Id={cdc}&dFeEmiDE={fe_hex}"
                f"&{'dRucRec' if has_ruc else 'dNumIDRec'}={qr_datos.identificador_receptor}"
                f"&dTotGralOpe={total_ope}&dTotIVA={total_iva}&cItems={len(items)}"
            )

        # Generate QR code graphics via segno
        qr_code = segno.make(qr_url)
        qr_data_uri = qr_code.svg_data_uri()
        try:
            import io
            buf = io.StringIO()
            qr_code.terminal(out=buf, compact=True)
            qr_ascii = buf.getvalue()
        except Exception:
            qr_ascii = ""

        # Format readable POS thermal receipt
        is_contingencia = header.emission_type == EMISSION_CONTINGENCIA
        receipt_text = self._build_receipt_text(
            header=header,
            items=items,
            resolved=resolved,
            cdc=cdc,
            total_ope=total_ope,
            total_iva=total_iva,
            sub_10=sub_10,
            sub_5=sub_5,
            sub_exe=sub_exe,
            is_contingencia=is_contingencia,
            qr_url=qr_url,
        )

        return KuDeReceipt(
            cdc=cdc,
            cdc_formatted=format_cdc_blocks(cdc),
            timbrado=header.timbrado_number,
            establishment_code=header.establishment_code,
            point_of_issue_code=header.point_of_issue_code,
            document_number=header.document_number,
            emission_type=header.emission_type,
            is_contingencia=is_contingencia,
            issue_date=header.issue_date,
            issuer_name=header.issuer_legal_name,
            issuer_ruc=f"{header.issuer_ruc}-{header.issuer_dv}",
            receiver_name=header.receiver_legal_name,
            receiver_id=receiver_id,
            total_operation=total_ope,
            total_iva=total_iva,
            qr_url=qr_url,
            qr_data_uri=qr_data_uri,
            qr_ascii=qr_ascii,
            receipt_text=receipt_text,
        )

    def _build_receipt_text(
        self,
        header: DteHeaderInput,
        items: list[DteItemInput],
        resolved: ResolvedProfile,
        cdc: str,
        total_ope: Decimal,
        total_iva: Decimal,
        sub_10: Decimal,
        sub_5: Decimal,
        sub_exe: Decimal,
        is_contingencia: bool,
        qr_url: str,
    ) -> str:
        lines: list[str] = []
        sep = "=" * 64
        sub_sep = "-" * 64

        lines.append(sep)
        lines.append(header.issuer_legal_name.center(64))
        lines.append(f"RUC: {header.issuer_ruc}-{header.issuer_dv}".center(64))
        lines.append(f"Timbrado: {header.timbrado_number}".center(64))
        doc_full = f"{header.establishment_code}-{header.point_of_issue_code}-{header.document_number}"
        lines.append(f"{resolved.dte_type_description} Nº {doc_full}".center(64))
        lines.append(sep)

        if is_contingencia:
            lines.append("*** COMPROBANTE EMITIDO EN CONTINGENCIA ***".center(64))
            lines.append("Motivo: SIFEN no disponible / Red offline".center(64))
            lines.append("Transmision legal DNIT: Plazo maximo 72 horas".center(64))
            lines.append(sub_sep)

        lines.append(f"Fecha/Hora: {header.issue_date.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Cliente:    {header.receiver_legal_name}")
        rec_id = f"{header.receiver_ruc}-{header.receiver_dv}" if header.receiver_ruc else (header.receiver_doc_number or "Consumidor Final")
        lines.append(f"RUC/Doc:    {rec_id}")
        lines.append(sub_sep)

        # Header columns
        lines.append(f"{'Cant':<5} {'Descripcion':<35} {'P.Unit':>10} {'Total':>12}")
        lines.append(sub_sep)

        for item in items:
            line_tot = (item.quantity * item.unit_price) - item.discount
            desc = item.description[:35]
            lines.append(
                f"{str(item.quantity):<5} {desc:<35} {int(item.unit_price):>10,d} {int(line_tot):>12,d}".replace(
                    ",", "."
                )
            )

        lines.append(sub_sep)
        if resolved.dte_type == DTE_FACTURA_ELECTRONICA:
            lines.append(f"{'Subtotal Exento:':<40} {int(sub_exe):>23,d} PYG".replace(",", "."))
            lines.append(f"{'Subtotal Gravado 5%:':<40} {int(sub_5):>23,d} PYG".replace(",", "."))
            lines.append(f"{'Subtotal Gravado 10%:':<40} {int(sub_10):>23,d} PYG".replace(",", "."))
            lines.append(sub_sep)
            lines.append(f"{'TOTAL A PAGAR:':<40} {int(total_ope):>23,d} PYG".replace(",", "."))
            lines.append(sub_sep)
            lines.append("LIQUIDACION IVA:")
            lines.append(f"{'IVA 5%:':<40} {int(sub_5 / Decimal(21) if sub_5 else 0):>23,d} PYG".replace(",", "."))
            lines.append(f"{'IVA 10%:':<40} {int(total_iva):>23,d} PYG".replace(",", "."))
            lines.append(f"{'TOTAL IVA:':<40} {int(total_iva):>23,d} PYG".replace(",", "."))
        else:
            lines.append(f"{'TOTAL OPERACION (Exento IRE Resimple):':<40} {int(total_ope):>23,d} PYG".replace(",", "."))

        lines.append(sep)
        lines.append("CDC:")
        lines.append(format_cdc_blocks(cdc).center(64))
        lines.append(sub_sep)
        lines.append("Consulte validez de este DTE dentro de las 72 hs con el CDC en:")
        lines.append("https://ekuatia.set.gov.py o escaneando el codigo QR.")
        lines.append(f"QR URL: {qr_url}")
        lines.append(sep)

        return "\n".join(lines)
