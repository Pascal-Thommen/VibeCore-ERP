"""
SIFEN Module Constants and Tax Regimes for Paraguay (SET / DNIT).
"""

from enum import StrEnum


class TaxRegime(StrEnum):
    """Paraguayan corporate and small-business income tax regimes."""

    IRE_GENERAL = "IRE_GENERAL"
    IRE_SIMPLE = "IRE_SIMPLE"
    IRE_RESIMPLE = "IRE_RESIMPLE"


# Official Obligation Codes (Códigos de Obligaciones tributarias SET/DNIT)
OBLIGACION_IRE_GENERAL = 700
OBLIGACION_IRE_SIMPLE = 701
OBLIGACION_IRE_RESIMPLE = 702

OBLIGACION_IVA_GENERAL = 211
OBLIGACION_IVA_SIMPLIFICADO = 212

OBLIGACION_DESCRIPTIONS = {
    OBLIGACION_IRE_GENERAL: "IRE REGIMEN GENERAL",
    OBLIGACION_IRE_SIMPLE: "IRE SIMPLE",
    OBLIGACION_IRE_RESIMPLE: "IRE RESIMPLE",
    OBLIGACION_IVA_GENERAL: "IVA GENERAL",
    OBLIGACION_IVA_SIMPLIFICADO: "IVA SIMPLIFICADO",
}

# SIFEN Electronic Document Types (iTiDE - Tipo de Documento Electrónico)
DTE_FACTURA_ELECTRONICA = 1
DTE_FACTURA_EXPORTACION = 2
DTE_FACTURA_IMPORTACION = 3
DTE_BOLETA_RESIMPLE = 4
DTE_NOTA_CREDITO = 5
DTE_NOTA_DEBITO = 6
DTE_AUTOFACTURA = 7
DTE_NOTA_REMISION = 8

DTE_TYPE_DESCRIPTIONS = {
    DTE_FACTURA_ELECTRONICA: "Factura electrónica",
    DTE_FACTURA_EXPORTACION: "Factura electrónica de exportación",
    DTE_FACTURA_IMPORTACION: "Factura electrónica de importación",
    DTE_BOLETA_RESIMPLE: "Boleta resimple electrónica",
    DTE_NOTA_CREDITO: "Nota de crédito electrónica",
    DTE_NOTA_DEBITO: "Nota de débito electrónica",
    DTE_AUTOFACTURA: "Autofactura electrónica",
    DTE_NOTA_REMISION: "Nota de remisión electrónica",
}

# SIFEN 2-digit codes for Core models and database compatibility
DTE_TYPE_CODES = {
    DTE_FACTURA_ELECTRONICA: "01",
    DTE_FACTURA_EXPORTACION: "02",
    DTE_FACTURA_IMPORTACION: "03",
    DTE_BOLETA_RESIMPLE: "04",
    DTE_NOTA_CREDITO: "05",
    DTE_NOTA_DEBITO: "06",
    DTE_AUTOFACTURA: "07",
    DTE_NOTA_REMISION: "08",
}

# SIFEN IVA Afectación (iAfecIVA)
IVA_AFECTACION_GRAVADO = 1
IVA_AFECTACION_EXONERADO = 2
IVA_AFECTACION_EXENTO = 3
IVA_AFECTACION_GRAVADO_PARCIAL = 4

IVA_AFECTACION_DESCRIPTIONS = {
    IVA_AFECTACION_GRAVADO: "Gravado IVA",
    IVA_AFECTACION_EXONERADO: "Exonerado",
    IVA_AFECTACION_EXENTO: "Exento",
    IVA_AFECTACION_GRAVADO_PARCIAL: "Gravado parcial",
}

# SIFEN XML Technical Specifications
SIFEN_XML_NAMESPACE = "http://ekuatia.set.gov.py/sifen/xsd"
SIFEN_FORMAT_VERSION = "150"
SIFEN_CURRENCY_PYG = "PYG"
