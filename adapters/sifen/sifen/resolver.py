"""
RUC Profile Resolver Service for VibeCore SIFEN Adapter.

Resolves a tenant's RUC obligations to determine:
1. DTE Document Type (Factura Electrónica vs Boleta Resimple Electrónica)
2. Tax Calculation Mode (Full IVA 10%/5%/Exento breakdown vs Gross tax-exempt)
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
        """Extract a normalized list of integer obligation codes from various input formats."""
        if isinstance(profile, MandantRucProfile):
            raw_obligaciones = profile.obligaciones
        elif isinstance(profile, dict):
            raw_obligaciones = (
                profile.get("obligaciones") or profile.get("obligations") or []
            )
        elif isinstance(profile, list):
            raw_obligaciones = profile
        else:
            raise TypeError(f"Ungueltiges RUC-Profilformat: {type(profile).__name__}")

        codes: list[int] = []
        for item in raw_obligaciones:
            if isinstance(item, int):
                codes.append(item)
            elif isinstance(item, str) and item.isdigit():
                codes.append(int(item))
            elif isinstance(item, MandantObligacion):
                codes.append(item.code)
            elif isinstance(item, dict) and "code" in item:
                codes.append(int(item["code"]))
            elif hasattr(item, "code"):
                codes.append(int(item.code))
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

        # Resolution hierarchy: 700 (General) > 701 (Simple) > 702 (Resimple)
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
        Calculate tax details for an item according to the resolved profile and SIFEN formula.

        SIFEN Formula:
        For IVA 10%:
          dBasGravIVA = (100 * line_total) / 110
          dLiqIVAItem = dBasGravIVA * 0.10 (or line_total / 11)
        For IVA 5%:
          dBasGravIVA = (100 * line_total) / 105
          dLiqIVAItem = dBasGravIVA * 0.05 (or line_total / 21)
        For IRE Resimple (702):
          No IVA calculation, tax-exempt marked, gross amount only.
        """
        line_total = (quantity * unit_price) - discount
        if line_total < Decimal(0):
            raise ValueError(f"Line total must not be negative: {line_total}")

        is_pyg = currency.upper() == SIFEN_CURRENCY_PYG

        # IRE Resimple (702): Keine IVA, nur Bruttoendbetrag
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

        # IRE General (700) and Simple (701): Full IVA resolution
        if tax_rate == Decimal(10):
            afectacion_iva = IVA_AFECTACION_GRAVADO
            des_afectacion = IVA_AFECTACION_DESCRIPTIONS[IVA_AFECTACION_GRAVADO]
            proporcion_iva = Decimal(100)
            tasa_iva = Decimal(10)

            if is_pyg:
                base_gravada = (line_total / Decimal("1.1")).quantize(
                    Decimal(1), rounding=ROUND_HALF_UP
                )
                liquidacion_iva = (line_total / Decimal(11)).quantize(
                    Decimal(1), rounding=ROUND_HALF_UP
                )
            else:
                base_gravada = (line_total / Decimal("1.1")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                liquidacion_iva = (base_gravada * Decimal("0.10")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

        elif tax_rate == Decimal(5):
            afectacion_iva = IVA_AFECTACION_GRAVADO
            des_afectacion = IVA_AFECTACION_DESCRIPTIONS[IVA_AFECTACION_GRAVADO]
            proporcion_iva = Decimal(100)
            tasa_iva = Decimal(5)

            if is_pyg:
                base_gravada = (line_total / Decimal("1.05")).quantize(
                    Decimal(1), rounding=ROUND_HALF_UP
                )
                liquidacion_iva = (line_total / Decimal(21)).quantize(
                    Decimal(1), rounding=ROUND_HALF_UP
                )
            else:
                base_gravada = (line_total / Decimal("1.05")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                liquidacion_iva = (base_gravada * Decimal("0.05")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

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
