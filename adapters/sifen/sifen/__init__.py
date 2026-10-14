"""
SIFEN Adapter Module for VibeCore ERP.
"""

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
    ItemTaxDetail,
    MandantObligacion,
    MandantRucProfile,
    ResolvedProfile,
)
from sifen.resolver import SifenProfileResolver
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
    "ItemTaxDetail",
    "MandantObligacion",
    "MandantRucProfile",
    "ResolvedProfile",
    "SifenProfileResolver",
    "SifenXmlGenerator",
    "TaxRegime",
    "compute_sifen_modulo_11",
    "generate_sifen_cdc",
]
