"""
SIFEN Digital Signing (XMLDSig) and QR code generation using pysifen.
"""

from __future__ import annotations

import base64
import os
import warnings
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    pkcs12,
)
from cryptography.x509.oid import NameOID
from lxml import etree
from pysifen.documento.sobre import agregar_campos_fuera_de_firma
from pysifen.enums import Ambiente
from pysifen.qr import DatosQr, generar_url_qr
from pysifen.security.secretos import Secreto
from pysifen.signing.backends.pkcs12 import AvisoDeCustodia, FirmantePkcs12
from pysifen.signing.xmldsig import firmar_documento

from sifen.models import DteHeaderInput

warnings.filterwarnings("ignore", category=AvisoDeCustodia)

DEFAULT_TEST_CSC = "ABCD0000000000000000000000000000"
DEFAULT_TEST_ID_CSC = "0001"


def generate_mock_pkcs12(
    ruc: str = "80011111",
    dv: str = "4",
    legal_name: str = "Comercio Grande S.A.",
    password: str = "vibecore123",
) -> tuple[bytes, str]:
    """Generate an in-memory self-signed PKCS#12 software certificate for testing."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "PY"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, legal_name),
            x509.NameAttribute(NameOID.COMMON_NAME, f"{ruc}-{dv}"),
        ]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )

    p12_bytes = pkcs12.serialize_key_and_certificates(
        name=b"vibecore_sifen_mock",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=BestAvailableEncryption(password.encode("utf-8")),
    )
    return p12_bytes, password


class SifenSigner:
    """Handles XMLDSig digital signature and QR-code attachment via pysifen."""

    def __init__(
        self,
        p12_bytes: bytes | None = None,
        p12_path: str | Path | None = None,
        password: str | None = None,
        allow_mock: bool = True,
    ) -> None:
        raw_p12 = p12_bytes
        pwd = password

        if raw_p12 is None and p12_path is None:
            env_b64 = os.environ.get("SIFEN_CERT_P12_BASE64")
            env_path = os.environ.get("SIFEN_CERT_PATH")
            env_pwd = os.environ.get("SIFEN_CERT_PASSWORD")

            if env_b64:
                raw_p12 = base64.b64decode(env_b64)
                pwd = pwd or env_pwd or ""
            elif env_path:
                p12_path = env_path
                pwd = pwd or env_pwd or ""
            elif allow_mock:
                raw_p12, pwd = generate_mock_pkcs12()

        if raw_p12 is not None:
            self.firmante = FirmantePkcs12.desde_bytes(
                raw_p12,
                Secreto(pwd or ""),
                permitir_clave_en_memoria=True,
            )
            self._p12_bytes = raw_p12
            self._password = pwd or ""
        elif p12_path is not None:
            self.firmante = FirmantePkcs12.desde_archivo(
                p12_path,
                Secreto(pwd or ""),
                permitir_clave_en_disco=True,
            )
            self._p12_bytes = Path(p12_path).read_bytes()
            self._password = pwd or ""
        else:
            raise ValueError(
                "No PKCS#12 certificate data or file provided for SIFEN signing."
            )

    @property
    def p12_bytes(self) -> bytes:
        return self._p12_bytes

    @property
    def password(self) -> str:
        return self._password

    def sign_xml(self, xml: str | bytes) -> bytes:
        """Sign XML content with XMLDSig using RSA-SHA256."""
        return firmar_documento(xml, self.firmante)

    def extract_qr_data_from_xml(
        self,
        root: etree._Element,
        id_csc: str,
        header: DteHeaderInput | None = None,
    ) -> DatosQr:
        """Extract all metadata required for QR code generation from signed XML."""
        de_elem = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}DE")
        if de_elem is None:
            raise ValueError("Root rDE does not contain valid DE element")

        cdc = de_elem.get("Id")
        if not cdc:
            raise ValueError("DE element missing Id attribute (CDC)")

        digest_elem = root.find(".//{http://www.w3.org/2000/09/xmldsig#}DigestValue")
        if digest_elem is None or not digest_elem.text:
            raise ValueError("Signed XML missing DigestValue")
        digest_value = digest_elem.text.strip()

        fe_elem = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dFeEmiDE")
        fecha_emision = fe_elem.text.strip() if fe_elem is not None and fe_elem.text else (
            header.issue_date if header else datetime.now(timezone.utc)
        )

        ruc_rec_elem = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dRucRec")
        num_id_rec_elem = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dNumIDRec")

        if ruc_rec_elem is not None and ruc_rec_elem.text:
            identificador_receptor = ruc_rec_elem.text.strip()
            receptor_con_ruc = True
        elif num_id_rec_elem is not None and num_id_rec_elem.text:
            identificador_receptor = num_id_rec_elem.text.strip()
            receptor_con_ruc = False
        else:
            identificador_receptor = None
            receptor_con_ruc = True

        tot_elem = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dTotGralOpe")
        total_general = Decimal(tot_elem.text.strip()) if tot_elem is not None and tot_elem.text else Decimal(0)

        iva_elem = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dTotIVA")
        total_iva = Decimal(iva_elem.text.strip()) if iva_elem is not None and iva_elem.text else Decimal(0)

        items = root.findall(".//{http://ekuatia.set.gov.py/sifen/xsd}gCamItem")
        cantidad_items = len(items) if items else 1

        ver_elem = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dVerFor")
        version = int(ver_elem.text.strip()) if ver_elem is not None and ver_elem.text else 150

        return DatosQr(
            cdc=cdc,
            fecha_emision=fecha_emision,
            digest_value=digest_value,
            id_csc=id_csc,
            identificador_receptor=identificador_receptor,
            receptor_con_ruc=receptor_con_ruc,
            total_general=total_general,
            total_iva=total_iva,
            cantidad_items=cantidad_items,
            version=version,
        )

    def sign_and_add_qr(
        self,
        raw_xml: str | bytes,
        csc: str | None = None,
        id_csc: str | None = None,
        ambiente: str | Ambiente = "test",
        header: DteHeaderInput | None = None,
    ) -> tuple[str, str, str, str]:
        """
        Sign XML with XMLDSig, compute official QR URL with pysifen, and inject gCamFuFD.

        Returns:
            (signed_xml_with_qr_str, qr_url, cdc, digest_value)
        """
        signed_bytes = self.sign_xml(raw_xml)
        root = etree.fromstring(signed_bytes)

        resolved_id_csc = id_csc or os.environ.get("SIFEN_CSC_ID", DEFAULT_TEST_ID_CSC)
        resolved_csc = csc or os.environ.get("SIFEN_CSC", DEFAULT_TEST_CSC)

        datos_qr = self.extract_qr_data_from_xml(
            root=root,
            id_csc=resolved_id_csc,
            header=header,
        )

        amb = (
            Ambiente.PRODUCCION
            if (isinstance(ambiente, str) and ambiente.lower() in ("prod", "production"))
            or ambiente == Ambiente.PRODUCCION
            else Ambiente.TEST
        )

        qr_url = generar_url_qr(
            datos=datos_qr,
            csc=Secreto(resolved_csc),
            ambiente=amb,
        )

        agregar_campos_fuera_de_firma(root, qr_url)

        final_xml_bytes = etree.tostring(
            root, encoding="utf-8", xml_declaration=True, pretty_print=True
        )
        final_xml_str = final_xml_bytes.decode("utf-8")

        return final_xml_str, qr_url, datos_qr.cdc, datos_qr.digest_value
