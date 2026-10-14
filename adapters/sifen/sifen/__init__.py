"""
SIFEN Adapter Module for VibeCore ERP.
"""

from sifen.client import SifenSoapClient, build_soap12_envelope, parse_sifen_soap_response
from sifen.constants import (
    DTE_BOLETA_RESIMPLE,
    DTE_FACTURA_ELECTRONICA,
    DTE_TYPE_CODES,
    DTE_TYPE_DESCRIPTIONS,
    OBLIGACION_IRE_GENERAL,
    OBLIGACION_IRE_RESIMPLE,
    OBLIGACION_IRE_SIMPLE,
    TaxRegime,
)
from sifen.models import (
    DteHeaderInput,
    DteItemInput,
    GenerateXmlRequest,
    ItemTaxDetail,
    MandantObligacion,
    MandantRucProfile,
    ResolvedProfile,
    SignAndSendRequest,
    SignAndSendResponse,
    SignRequest,
    SignResponse,
)
from sifen.resolver import SifenProfileResolver
from sifen.server import app
from sifen.signer import SifenSigner, generate_mock_pkcs12
from sifen.xml_generator import (
    SifenXmlGenerator,
    compute_sifen_modulo_11,
    generate_sifen_cdc,
)

__all__ = [
    "DTE_BOLETA_RESIMPLE",
    "DTE_FACTURA_ELECTRONICA",
    "DTE_TYPE_CODES",
    "DTE_TYPE_DESCRIPTIONS",
    "OBLIGACION_IRE_GENERAL",
    "OBLIGACION_IRE_RESIMPLE",
    "OBLIGACION_IRE_SIMPLE",
    "DteHeaderInput",
    "DteItemInput",
    "GenerateXmlRequest",
    "ItemTaxDetail",
    "MandantObligacion",
    "MandantRucProfile",
    "ResolvedProfile",
    "SignAndSendRequest",
    "SignAndSendResponse",
    "SignRequest",
    "SignResponse",
    "SifenProfileResolver",
    "SifenSigner",
    "SifenSoapClient",
    "SifenXmlGenerator",
    "TaxRegime",
    "app",
    "build_soap12_envelope",
    "compute_sifen_modulo_11",
    "generate_mock_pkcs12",
    "generate_sifen_cdc",
    "parse_sifen_soap_response",
]
