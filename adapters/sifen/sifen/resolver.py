"""
RUC Profile Resolver Service for VibeCore SIFEN Adapter.

Resolves a tenant's RUC obligations to determine:
1. DTE Document Type (Factura Electrónica vs Boleta Resimple Electrónica)
2. Tax Calculation Mode (Gross-inclusive IVA 10%/5%/Exento per Ley 6380/19 vs Gross tax-exempt)
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sifen.constants import (
    IVA_AFECTACION_DESCRIPTIONS,
    IVA_AFECTACION_EXENTO,
    IVA_AFECTACION_GRAVADO,
    OBLIGACION_IRE_GENERAL,
    OBLIGACION_IRE_RESIMPLE,
    OBLIGACION_IRE_SIMPLE,
    SIFEN_CURRENCY_PYG,
    TaxRegime,
)
from sifen.models import (
    ItemTaxDetail,
    MandantObligacion,
    MandantRucProfile,
    ResolvedProfile,
)


class SifenProfileResolver:
    """Service to resolve Mandant RUC profile into SIFEN DTE and tax policies."""

    @classmethod
    def extract_obligation_codes(
        cls, profile: MandantRucProfile | dict[str, Any] | list[Any]
    ) -> list[int]:
        """Extract a normalized list of integer obligation codes."""
        if isinstance(profile, MandantRucProfile):
            raw_obligaciones = profile.obligaciones
        elif isinstance(profile, dict):
            raw_obligaciones = profile.get("obligaciones", [])
        elif isinstance(profile, list):
            raw_obligaciones = profile
        else:
            raise TypeError(f"Ungueltiges RUC-Profilformat: {type(profile).__name__}")

        codes: list[int] = []
        for item in raw_obligaciones:
            if isinstance(item, int) and not isinstance(item, bool):
                codes.append(item)
            elif isinstance(item, MandantObligacion):
                codes.append(item.code)
            elif isinstance(item, dict) and "code" in item:
                codes.append(int(item["code"]))
            else:
                raise ValueError(
                    f"Ungueltiger Steuerpflicht-Eintrag (Obligacion): {item}"
                )

        return codes

    @classmethod
    def resolve(
        cls, profile: MandantRucProfile | dict[str, Any] | list[Any]
    ) -> ResolvedProfile:
        """
        Resolve the Mandant's RUC profile into DTE Type and tax behavior.

        Obligation rules:
        - 700: IRE General -> Factura Electrónica (iTiDE = 1), IVA 10%/5%/Exento calculation
        - 701: IRE Simple -> Factura Electrónica (iTiDE = 1), IVA 10%/5%/Exento calculation
        - 702: IRE Resimple -> Boleta Resimple Electrónica (iTiDE = 4), keine IVA (nur Brutto)
        """
        codes = cls.extract_obligation_codes(profile)

        if OBLIGACION_IRE_GENERAL in codes:
            return ResolvedProfile.from_regime(
                TaxRegime.IRE_GENERAL, OBLIGACION_IRE_GENERAL
            )

        if OBLIGACION_IRE_SIMPLE in codes:
            return ResolvedProfile.from_regime(
                TaxRegime.IRE_SIMPLE, OBLIGACION_IRE_SIMPLE
            )

        if OBLIGACION_IRE_RESIMPLE in codes:
            return ResolvedProfile.from_regime(
                TaxRegime.IRE_RESIMPLE, OBLIGACION_IRE_RESIMPLE
            )

        raise ValueError(
            f"Keine gueltige IRE-Steuerpflicht (Code 700: IRE General, 701: IRE Simple, "
            f"702: IRE Resimple) im Mandanten-Profil gefunden: {codes}"
        )

    @classmethod
    def calculate_item_tax(
        cls,
        resolved: ResolvedProfile,
        quantity: Decimal,
        unit_price: Decimal,
        discount: Decimal = Decimal(0),
        tax_rate: Decimal = Decimal(10),
        currency: str = SIFEN_CURRENCY_PYG,
    ) -> ItemTaxDetail:
        """
        Calculate tax details for an item according to Ley 6380/19 and SIFEN Technical Manual v150.

        Guarantees exact balance (base_gravada + liquidacion_iva == total_item) without rounding drift:
        - IVA 10%: liquidacion_iva = round(line_total / 11), base_gravada = line_total - liquidacion_iva
        - IVA 5%:  liquidacion_iva = round(line_total / 21), base_gravada = line_total - liquidacion_iva
        - IRE Resimple (702) or Exento (0%): liquidacion_iva = 0, base_gravada = 0
        """
        raw_total = (quantity * unit_price) - discount
        if raw_total < Decimal(0):
            raise ValueError(f"Line total must not be negative: {raw_total}")

        quantum = Decimal(1) if currency.upper() == SIFEN_CURRENCY_PYG else Decimal("0.01")
        line_total = raw_total.quantize(quantum, rounding=ROUND_HALF_UP)

        if not resolved.iva_applicable:
            return ItemTaxDetail(
                afectacion_iva=IVA_AFECTACION_EXENTO,
                des_afectacion_iva=IVA_AFECTACION_DESCRIPTIONS[IVA_AFECTACION_EXENTO],
                proporcion_iva=Decimal(0),
                tasa_iva=Decimal(0),
                base_gravada=Decimal(0),
                liquidacion_iva=Decimal(0),
                total_item=line_total,
            )

        if tax_rate == Decimal(10):
            afectacion_iva = IVA_AFECTACION_GRAVADO
            des_afectacion = IVA_AFECTACION_DESCRIPTIONS[IVA_AFECTACION_GRAVADO]
            proporcion_iva = Decimal(100)
            tasa_iva = Decimal(10)
            liquidacion_iva = (line_total / Decimal(11)).quantize(
                quantum, rounding=ROUND_HALF_UP
            )
            base_gravada = line_total - liquidacion_iva

        elif tax_rate == Decimal(5):
            afectacion_iva = IVA_AFECTACION_GRAVADO
            des_afectacion = IVA_AFECTACION_DESCRIPTIONS[IVA_AFECTACION_GRAVADO]
            proporcion_iva = Decimal(100)
            tasa_iva = Decimal(5)
            liquidacion_iva = (line_total / Decimal(21)).quantize(
                quantum, rounding=ROUND_HALF_UP
            )
            base_gravada = line_total - liquidacion_iva

        elif tax_rate == Decimal(0):
            afectacion_iva = IVA_AFECTACION_EXENTO
            des_afectacion = IVA_AFECTACION_DESCRIPTIONS[IVA_AFECTACION_EXENTO]
            proporcion_iva = Decimal(0)
            tasa_iva = Decimal(0)
            base_gravada = Decimal(0)
            liquidacion_iva = Decimal(0)

        else:
            raise ValueError(
                f"Nicht unterstuetzter IVA-Steuersatz fuer SIFEN: {tax_rate}% (Gueltig: 10, 5, 0)"
            )

        return ItemTaxDetail(
            afectacion_iva=afectacion_iva,
            des_afectacion_iva=des_afectacion,
            proporcion_iva=proporcion_iva,
            tasa_iva=tasa_iva,
            base_gravada=base_gravada,
            liquidacion_iva=liquidacion_iva,
            total_item=line_total,
        )
