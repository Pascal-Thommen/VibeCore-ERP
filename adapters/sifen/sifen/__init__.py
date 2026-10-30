"""
SIFEN Adapter Module for VibeCore ERP.
"""

from sifen.client import SifenClient, SifenError, SifenNetworkError, SifenNotFoundError
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
    DteOutboxResponse,
    GenerateXmlRequest,
    ItemTaxDetail,
    MandantObligacion,
    MandantRucProfile,
    OutboxFlushResponse,
    OutboxStatus,
    ResolvedProfile,
    SubmitDteRequest,
)
from sifen.resolver import SifenProfileResolver
from sifen.service import SifenService
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
    "DteOutboxResponse",
    "GenerateXmlRequest",
    "ItemTaxDetail",
    "MandantObligacion",
    "MandantRucProfile",
    "OutboxFlushResponse",
    "OutboxStatus",
    "ResolvedProfile",
    "SifenClient",
    "SifenError",
    "SifenNetworkError",
    "SifenNotFoundError",
    "SifenProfileResolver",
    "SifenService",
    "SifenXmlGenerator",
    "SubmitDteRequest",
    "TaxRegime",
    "compute_sifen_modulo_11",
    "generate_sifen_cdc",
]
