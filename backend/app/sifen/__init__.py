"""
SIFEN Dynamic DTE and RUC Profile Resolver Module for VibeCore ERP.
"""

from app.sifen.constants import (
    DTE_BOLETA_RESIMPLE,
    DTE_FACTURA_ELECTRONICA,
    DTE_TYPE_CODES,
    DTE_TYPE_DESCRIPTIONS,
    OBLIGACION_IRE_GENERAL,
    OBLIGACION_IRE_RESIMPLE,
    OBLIGACION_IRE_SIMPLE,
    TaxRegime,
)
from app.sifen.models import (
    DteHeaderInput,
    DteItemInput,
    ItemTaxDetail,
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

__all__ = [
    "DTE_BOLETA_RESIMPLE",
    "DTE_FACTURA_ELECTRONICA",
    "DTE_TYPE_CODES",
    "DTE_TYPE_DESCRIPTIONS",
    "DteHeaderInput",
    "DteItemInput",
    "ItemTaxDetail",
    "MandantObligacion",
    "MandantRucProfile",
    "OBLIGACION_IRE_GENERAL",
    "OBLIGACION_IRE_RESIMPLE",
    "OBLIGACION_IRE_SIMPLE",
    "ResolvedProfile",
    "SifenProfileResolver",
    "SifenXmlGenerator",
    "TaxRegime",
    "compute_sifen_modulo_11",
    "generate_sifen_cdc",
]
