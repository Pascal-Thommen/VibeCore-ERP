"""
SOAP 1.2 client for SIFEN / DNIT e-Kuatia synchronization with mTLS support.
"""

from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

from sifen.models import SignAndSendResponse

DNIT_TEST_SOAP_URL = "https://sifen-test.set.gov.py/de/ws/sync/recibe"
DNIT_PROD_SOAP_URL = "https://sifen.set.gov.py/de/ws/sync/recibe"
SIFEN_XML_NS = "http://ekuatia.set.gov.py/sifen/xsd"
SOAP12_NS = "http://www.w3.org/2003/05/soap-envelope"


def clean_xml_for_soap_envelope(xml_str: str) -> str:
    """Strip XML declaration so the inner document can nest cleanly inside xDE."""
    stripped = re.sub(r"^\s*<\?xml[^>]*\?>", "", xml_str).strip()
    return stripped


def build_soap12_envelope(signed_rde_xml: str, doc_id: str = "1") -> str:
    """Build official SOAP 1.2 envelope for SIFEN siRecepDE."""
    inner_xml = clean_xml_for_soap_envelope(signed_rde_xml)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<soap12:Envelope xmlns:soap12="{SOAP12_NS}" xmlns:sifen="{SIFEN_XML_NS}">\n'
        "  <soap12:Body>\n"
        "    <sifen:rEnviDe>\n"
        f"      <sifen:dId>{doc_id}</sifen:dId>\n"
        f"      <sifen:xDE>\n"
        f"        {inner_xml}\n"
        "      </sifen:xDE>\n"
        "    </sifen:rEnviDe>\n"
        "  </soap12:Body>\n"
        "</soap12:Envelope>"
    )


def parse_sifen_soap_response(
    response_text: str,
) -> tuple[bool, str, str | None, str | None, str | None]:
    """
    Parse DNIT SOAP 1.2 response to extract result codes and processing message.

    Returns:
        (success, status, dCodRes, dMsgRes, dFecProc)
    """
    try:
        root = ET.fromstring(response_text)
    except ET.ParseError:
        return False, "Error", None, "Invalid XML received from SIFEN service", None

    # Check for SOAP Fault
    fault_elem = root.find(f".//{{{SOAP12_NS}}}Fault") or root.find(".//Fault")
    if fault_elem is not None:
        reason_elem = fault_elem.find(f".//{{{SOAP12_NS}}}Text") or fault_elem.find(".//Text")
        reason = reason_elem.text if reason_elem is not None else "SOAP Fault"
        return False, "SoapFault", "9999", reason, None

    def find_node(tag_name: str) -> ET.Element | None:
        elem = root.find(f".//{{{SIFEN_XML_NS}}}{tag_name}")
        if elem is not None:
            return elem
        for node in root.iter():
            if node.tag.split("}")[-1] == tag_name:
                return node
        return None

    cod_res_elem = find_node("dCodRes")
    msg_res_elem = find_node("dMsgRes")
    fec_proc_elem = find_node("dFecProc")

    d_cod_res = cod_res_elem.text.strip() if cod_res_elem is not None and cod_res_elem.text else None
    d_msg_res = msg_res_elem.text.strip() if msg_res_elem is not None and msg_res_elem.text else None
    d_fec_proc = fec_proc_elem.text.strip() if fec_proc_elem is not None and fec_proc_elem.text else None

    # Official SIFEN approved codes: 0260 (Aprobado), 0500 (Aprobado con observaciones)
    if d_cod_res in ("0260", "0500"):
        return True, "Aprobado", d_cod_res, d_msg_res or "Aprobado", d_fec_proc

    if d_cod_res:
        return False, "Rechazado", d_cod_res, d_msg_res or "Rechazado por SIFEN", d_fec_proc

    return True, "Enviado", None, d_msg_res or "Documento transmitido", d_fec_proc


class SifenSoapClient:
    """Client for transmitting signed SIFEN documents to DNIT using SOAP 1.2 and mTLS."""

    def __init__(
        self,
        endpoint_url: str | None = None,
        p12_bytes: bytes | None = None,
        password: str | None = None,
        simulation: bool = False,
        timeout: float = 30.0,
    ) -> None:
        self.endpoint_url = (
            endpoint_url
            or os.environ.get("SIFEN_SOAP_URL")
            or (DNIT_PROD_SOAP_URL if os.environ.get("SIFEN_ENV") == "prod" else DNIT_TEST_SOAP_URL)
        )
        self.p12_bytes = p12_bytes
        self.password = password or ""
        self.simulation = simulation or os.environ.get("SIFEN_SIMULATION", "false").lower() in ("true", "1", "yes")
        self.timeout = timeout

    def send_document(
        self,
        signed_xml: str,
        cdc: str,
        qr_url: str,
        doc_id: str | None = None,
        force_simulation: bool | None = None,
    ) -> SignAndSendResponse:
        """
        Transmit the signed document to SIFEN endpoint via SOAP 1.2.
        Supports mTLS authentication and simulated responses.
        """
        is_simulation = self.simulation if force_simulation is None else force_simulation
        d_id = doc_id or cdc[:10]

        if is_simulation:
            proc_time = datetime.now(timezone.utc).isoformat()
            raw_sim = (
                f'<soap12:Envelope xmlns:soap12="{SOAP12_NS}">\n'
                f'  <soap12:Body>\n'
                f'    <rRetEnviDe xmlns="{SIFEN_XML_NS}">\n'
                f'      <dFecProc>{proc_time}</dFecProc>\n'
                f'      <rProtDe>\n'
                f'        <Id>{cdc}</Id>\n'
                f'        <dFecProc>{proc_time}</dFecProc>\n'
                f'        <gResProc>\n'
                f'          <dCodRes>0260</dCodRes>\n'
                f'          <dMsgRes>Aprobado</dMsgRes>\n'
                f'        </gResProc>\n'
                f'      </rProtDe>\n'
                f'    </rRetEnviDe>\n'
                f'  </soap12:Body>\n'
                f'</soap12:Envelope>'
            )
            return SignAndSendResponse(
                success=True,
                cdc=cdc,
                status="Aprobado",
                dCodRes="0260",
                dMsgRes="Aprobado",
                dFecProc=proc_time,
                qr_url=qr_url,
                xml_signed=signed_xml,
                raw_response=raw_sim,
            )

        envelope = build_soap12_envelope(signed_xml, doc_id=d_id)
        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
            "Accept": "application/soap+xml, text/xml",
        }

        # Prepare mTLS certificate files if PKCS#12 is provided
        cert_arg = None
        temp_files: list[Path] = []

        try:
            if self.p12_bytes:
                try:
                    loaded_key, loaded_cert, _ = pkcs12.load_key_and_certificates(
                        self.p12_bytes, self.password.encode("utf-8")
                    )
                    if loaded_key and loaded_cert:
                        key_pem = loaded_key.private_bytes(
                            serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption(),
                        )
                        cert_pem = loaded_cert.public_bytes(serialization.Encoding.PEM)

                        k_file = tempfile.NamedTemporaryFile("wb", delete=False)
                        k_file.write(key_pem)
                        k_file.close()
                        temp_files.append(Path(k_file.name))

                        c_file = tempfile.NamedTemporaryFile("wb", delete=False)
                        c_file.write(cert_pem)
                        c_file.close()
                        temp_files.append(Path(c_file.name))

                        cert_arg = (c_file.name, k_file.name)
                except Exception:
                    pass

            with httpx.Client(cert=cert_arg, timeout=self.timeout) as client:
                response = client.post(
                    self.endpoint_url,
                    content=envelope.encode("utf-8"),
                    headers=headers,
                )
                raw_text = response.text

            success, status, d_cod, d_msg, d_fec = parse_sifen_soap_response(raw_text)

            return SignAndSendResponse(
                success=success,
                cdc=cdc,
                status=status,
                dCodRes=d_cod,
                dMsgRes=d_msg,
                dFecProc=d_fec,
                qr_url=qr_url,
                xml_signed=signed_xml,
                raw_response=raw_text,
            )

        except Exception as exc:
            # Handle network/connection failure gracefully
            return SignAndSendResponse(
                success=False,
                cdc=cdc,
                status="Error",
                dCodRes="9999",
                dMsgRes=f"Transmission error: {exc}",
                dFecProc=datetime.now(timezone.utc).isoformat(),
                qr_url=qr_url,
                xml_signed=signed_xml,
                raw_response=None,
            )

        finally:
            for p in temp_files:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
