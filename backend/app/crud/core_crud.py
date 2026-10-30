"""Asynchronous SQLAlchemy 2.0 persistence operations for the Finance Core.

This module contains no HTTP concerns.  Routers translate its ``None`` returns
and domain exceptions into HTTP responses, leaving the Core rules reusable by
other authenticated entry points.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Account, Document, DocumentItem, Partner, Product, Tax
from app.schemas.core_schemas import (
    AccountCreate,
    AccountUpdate,
    DocumentCreate,
    DocumentItemCreate,
    DocumentUpdate,
    PartnerCreate,
    PartnerUpdate,
    ProductCreate,
    ProductUpdate,
    TaxCreate,
    TaxUpdate,
)

MONEY_QUANTUM = Decimal("0.000001")
PYG_QUANTUM = Decimal("1")


class DocumentNotEditableError(Exception):
    """Raised when an operation would mutate a non-DRAFT financial document."""


class RelatedResourceNotFoundError(Exception):
    """Raised when an entity references a resource that does not exist."""


class PartnerDirectionError(Exception):
    """Raised when a document direction conflicts with the partner's fiscal role."""


class TaxScopeError(Exception):
    """Raised when a tax cannot be used in the document direction."""


def _schema_values(schema: Any) -> dict[str, Any]:
    return schema.model_dump(exclude_unset=True, by_alias=False)


def _money(value: Decimal, currency_code: str = "USD") -> Decimal:
    """Round to PYG whole integers (no centavos) or Core NUMERIC(20, 6) storage precision."""
    quantum = PYG_QUANTUM if currency_code.upper() == "PYG" else MONEY_QUANTUM
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def calculate_paraguayan_iva(
    gross_amount: Decimal, tax_rate: Decimal, currency_code: str = "PYG"
) -> tuple[Decimal, Decimal, Decimal]:
    """Calculate Paraguayan tax-inclusive IVA (Ley 6380/19) from gross line total.

    Official tax liquidation formulas:
    - IVA 10%: liquidacion_iva = gross_amount / 11
    - IVA 5%:  liquidacion_iva = gross_amount / 21
    - Exenta (0%): liquidacion_iva = 0
    Returns (net_subtotal, tax_amount, gross_total) where net_subtotal + tax_amount == gross_total.
    """
    gross_total = _money(gross_amount, currency_code)
    if tax_rate == Decimal("10"):
        tax_amount = _money(gross_total / Decimal("11"), currency_code)
    elif tax_rate == Decimal("5"):
        tax_amount = _money(gross_total / Decimal("21"), currency_code)
    elif tax_rate == Decimal("0"):
        tax_amount = _money(Decimal("0"), currency_code)
    else:
        tax_amount = _money(
            gross_total * tax_rate / (Decimal("100") + tax_rate), currency_code
        )
    net_subtotal = _money(gross_total - tax_amount, currency_code)
    return net_subtotal, tax_amount, gross_total


async def _commit_and_refresh(session: AsyncSession, entity: Any) -> Any:
    await session.commit()
    await session.refresh(entity)
    return entity


async def _get_active_partner_for_direction(
    session: AsyncSession, partner_id: UUID, direction: str
) -> Partner:
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise RelatedResourceNotFoundError("partner")
    if not partner.is_active:
        raise PartnerDirectionError("inactive partner")
    if direction == "SALES" and not partner.is_customer:
        raise PartnerDirectionError("sales documents require a customer partner")
    if direction == "PURCHASE" and not partner.is_supplier:
        raise PartnerDirectionError("purchase documents require a supplier partner")
    return partner


async def _get_tax_for_direction(session: AsyncSession, tax_id: UUID, direction: str) -> Tax:
    tax = await session.get(Tax, tax_id)
    if tax is None:
        raise RelatedResourceNotFoundError("tax")
    if not tax.is_active or tax.scope not in ("BOTH", direction):
        raise TaxScopeError("tax is inactive or not valid for the document direction")
    return tax


async def _require_product_if_present(session: AsyncSession, product_id: UUID | None) -> None:
    if product_id is not None and await session.get(Product, product_id) is None:
        raise RelatedResourceNotFoundError("product")


async def _require_document_if_present(session: AsyncSession, document_id: UUID | None) -> None:
    if document_id is not None and await session.get(Document, document_id) is None:
        raise RelatedResourceNotFoundError("associated document")


async def get_partner(session: AsyncSession, partner_id: UUID) -> Partner | None:
    return await session.get(Partner, partner_id)


async def list_partners(
    session: AsyncSession, *, offset: int = 0, limit: int = 100
) -> list[Partner]:
    statement = select(Partner).order_by(Partner.legal_name).offset(offset).limit(limit)
    result = await session.scalars(statement)
    return list(result)


async def create_partner(session: AsyncSession, data: PartnerCreate) -> Partner:
    partner = Partner(**_schema_values(data))
    session.add(partner)
    return await _commit_and_refresh(session, partner)


async def update_partner(
    session: AsyncSession, partner_id: UUID, data: PartnerUpdate
) -> Partner | None:
    partner = await get_partner(session, partner_id)
    if partner is None:
        return None
    for field, value in _schema_values(data).items():
        setattr(partner, field, value)
    return await _commit_and_refresh(session, partner)


async def delete_partner(session: AsyncSession, partner_id: UUID) -> bool:
    partner = await get_partner(session, partner_id)
    if partner is None:
        return False
    await session.delete(partner)
    await session.commit()
    return True


async def get_account(session: AsyncSession, account_id: UUID) -> Account | None:
    return await session.get(Account, account_id)


async def list_accounts(
    session: AsyncSession, *, offset: int = 0, limit: int = 100
) -> list[Account]:
    statement = select(Account).order_by(Account.code).offset(offset).limit(limit)
    result = await session.scalars(statement)
    return list(result)


async def create_account(session: AsyncSession, data: AccountCreate) -> Account:
    values = _schema_values(data)
    parent_id = values.get("parent_id")
    if parent_id is not None and await get_account(session, parent_id) is None:
        raise RelatedResourceNotFoundError("parent account")
    account = Account(**values)
    session.add(account)
    return await _commit_and_refresh(session, account)


async def update_account(
    session: AsyncSession, account_id: UUID, data: AccountUpdate
) -> Account | None:
    account = await get_account(session, account_id)
    if account is None:
        return None
    values = _schema_values(data)
    parent_id = values.get("parent_id")
    if parent_id is not None:
        if parent_id == account_id:
            raise ValueError("an account cannot be its own parent")
        if await get_account(session, parent_id) is None:
            raise RelatedResourceNotFoundError("parent account")
    for field, value in values.items():
        setattr(account, field, value)
    return await _commit_and_refresh(session, account)


async def delete_account(session: AsyncSession, account_id: UUID) -> bool:
    account = await get_account(session, account_id)
    if account is None:
        return False
    await session.delete(account)
    await session.commit()
    return True


async def get_tax(session: AsyncSession, tax_id: UUID) -> Tax | None:
    return await session.get(Tax, tax_id)


async def list_taxes(session: AsyncSession, *, offset: int = 0, limit: int = 100) -> list[Tax]:
    result = await session.scalars(select(Tax).order_by(Tax.code).offset(offset).limit(limit))
    return list(result)


async def _require_account_if_present(session: AsyncSession, account_id: UUID | None) -> None:
    if account_id is not None and await get_account(session, account_id) is None:
        raise RelatedResourceNotFoundError("account")


async def create_tax(session: AsyncSession, data: TaxCreate) -> Tax:
    values = _schema_values(data)
    await _require_account_if_present(session, values.get("sales_account_id"))
    await _require_account_if_present(session, values.get("purchase_account_id"))
    tax = Tax(**values)
    session.add(tax)
    return await _commit_and_refresh(session, tax)


async def update_tax(session: AsyncSession, tax_id: UUID, data: TaxUpdate) -> Tax | None:
    tax = await get_tax(session, tax_id)
    if tax is None:
        return None
    values = _schema_values(data)
    await _require_account_if_present(session, values.get("sales_account_id"))
    await _require_account_if_present(session, values.get("purchase_account_id"))
    for field, value in values.items():
        setattr(tax, field, value)
    return await _commit_and_refresh(session, tax)


async def delete_tax(session: AsyncSession, tax_id: UUID) -> bool:
    tax = await get_tax(session, tax_id)
    if tax is None:
        return False
    await session.delete(tax)
    await session.commit()
    return True


async def get_product(session: AsyncSession, product_id: UUID) -> Product | None:
    return await session.get(Product, product_id)


async def list_products(
    session: AsyncSession, *, offset: int = 0, limit: int = 100
) -> list[Product]:
    statement = select(Product).order_by(Product.sku).offset(offset).limit(limit)
    result = await session.scalars(statement)
    return list(result)


async def _validate_product_references(values: dict[str, Any], session: AsyncSession) -> None:
    if "default_tax_id" in values and values["default_tax_id"] is not None:
        if await get_tax(session, values["default_tax_id"]) is None:
            raise RelatedResourceNotFoundError("default tax")
    await _require_account_if_present(session, values.get("income_account_id"))
    await _require_account_if_present(session, values.get("expense_account_id"))


async def create_product(session: AsyncSession, data: ProductCreate) -> Product:
    values = _schema_values(data)
    await _validate_product_references(values, session)
    product = Product(**values)
    session.add(product)
    return await _commit_and_refresh(session, product)


async def update_product(
    session: AsyncSession, product_id: UUID, data: ProductUpdate
) -> Product | None:
    product = await get_product(session, product_id)
    if product is None:
        return None
    values = _schema_values(data)
    await _validate_product_references(values, session)
    for field, value in values.items():
        setattr(product, field, value)
    return await _commit_and_refresh(session, product)


async def delete_product(session: AsyncSession, product_id: UUID) -> bool:
    product = await get_product(session, product_id)
    if product is None:
        return False
    await session.delete(product)
    await session.commit()
    return True


async def get_document(session: AsyncSession, document_id: UUID) -> Document | None:
    statement = (
        select(Document)
        .options(selectinload(Document.items))
        .where(Document.id == document_id)
    )
    return (await session.scalars(statement)).one_or_none()


async def list_documents(
    session: AsyncSession, *, offset: int = 0, limit: int = 100
) -> list[Document]:
    statement = (
        select(Document)
        .options(selectinload(Document.items))
        .order_by(Document.issued_at.desc(), Document.id)
        .offset(offset)
        .limit(limit)
    )
    return list(await session.scalars(statement))


async def _line_values(
    session: AsyncSession,
    *,
    data: DocumentItemCreate | dict[str, Any],
    direction: str,
    currency_code: str,
    functional_currency_code: str,
    exchange_rate: Decimal,
    existing: DocumentItem | None = None,
) -> dict[str, Any]:
    """Resolve references and generate immutable tax and currency snapshots."""
    raw_values = data if isinstance(data, dict) else _schema_values(data)
    existing_values = {
        "product_id": existing.product_id if existing else None,
        "tax_id": existing.tax_id if existing else None,
        "product_code": existing.product_code if existing else None,
        "description": existing.description if existing else None,
        "unit_of_measure": existing.unit_of_measure if existing else None,
        "quantity": existing.quantity if existing else None,
        "unit_price": existing.unit_price if existing else None,
        "discount_amount": existing.discount_amount if existing else Decimal("0"),
    }
    values = {**existing_values, **raw_values}
    required = ("tax_id", "description", "unit_of_measure", "quantity", "unit_price")
    if any(values[field] is None for field in required):
        raise ValueError(
            "tax_id, description, unit_of_measure, quantity, and unit_price are required"
        )

    await _require_product_if_present(session, values["product_id"])
    tax = await _get_tax_for_direction(session, values["tax_id"], direction)
    gross = values["quantity"] * values["unit_price"]
    if values["discount_amount"] > gross:
        raise ValueError("discount_amount cannot exceed quantity multiplied by unit_price")

    gross_after_discount = gross - values["discount_amount"]
    line_subtotal, tax_amount, line_total = calculate_paraguayan_iva(
        gross_after_discount, tax.rate, currency_code
    )
    functional_gross = gross_after_discount * exchange_rate
    functional_subtotal, functional_tax_amount, functional_total = calculate_paraguayan_iva(
        functional_gross, tax.rate, functional_currency_code
    )

    return {
        **values,
        "tax_rate": tax.rate,
        "line_subtotal": line_subtotal,
        "tax_amount": tax_amount,
        "line_total": line_total,
        "functional_unit_price": _money(
            values["unit_price"] * exchange_rate, functional_currency_code
        ),
        "functional_subtotal": functional_subtotal,
        "functional_tax_amount": functional_tax_amount,
        "functional_total": functional_total,
    }


def _apply_document_totals(document: Document, items: list[DocumentItem]) -> None:
    currency = document.currency_code
    func_currency = document.functional_currency_code
    document.subtotal = _money(
        sum((item.line_subtotal for item in items), Decimal("0")), currency
    )
    document.tax_total = _money(
        sum((item.tax_amount for item in items), Decimal("0")), currency
    )
    document.total = _money(document.subtotal + document.tax_total, currency)
    document.functional_subtotal = _money(
        sum((item.functional_subtotal for item in items), Decimal("0")), func_currency
    )
    document.functional_tax_total = _money(
        sum((item.functional_tax_amount for item in items), Decimal("0")), func_currency
    )
    document.functional_total = _money(
        document.functional_subtotal + document.functional_tax_total, func_currency
    )
    document.total_quantity = sum((item.quantity for item in items), Decimal("0")).quantize(
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )


async def create_document(session: AsyncSession, data: DocumentCreate) -> Document:
    partner = await _get_active_partner_for_direction(session, data.partner_id, data.direction)
    await _require_document_if_present(session, data.associated_document_id)
    document_values = _schema_values(data)
    item_data = document_values.pop("items")
    # Financial lifecycle policy: all API-created documents begin as DRAFT.
    document_values.update(
        {
            "status": "DRAFT",
            "functional_currency_code": data.functional_currency_code,
            "exchange_rate": data.exchange_rate,
            "partner_ruc": partner.ruc,
            "partner_dv": partner.dv,
            "partner_legal_name": partner.legal_name,
        }
    )
    document = Document(**document_values)
    session.add(document)
    await session.flush()

    items: list[DocumentItem] = []
    for line_number, item in enumerate(item_data, start=1):
        values = await _line_values(
            session,
            data=item,
            direction=document.direction,
            currency_code=document.currency_code,
            functional_currency_code=document.functional_currency_code,
            exchange_rate=document.exchange_rate,
        )
        line = DocumentItem(document_id=document.id, line_number=line_number, **values)
        session.add(line)
        items.append(line)
    _apply_document_totals(document, items)
    await session.commit()
    return (await get_document(session, document.id))  # type: ignore[return-value]


async def update_document(
    session: AsyncSession, document_id: UUID, data: DocumentUpdate
) -> Document | None:
    document = await get_document(session, document_id)
    if document is None:
        return None
    if document.status != "DRAFT":
        raise DocumentNotEditableError("only DRAFT documents can be changed")
    values = _schema_values(data)
    if "partner_id" in values:
        partner = await _get_active_partner_for_direction(
            session, values["partner_id"], document.direction
        )
        values.update(
            {
                "partner_ruc": partner.ruc,
                "partner_dv": partner.dv,
                "partner_legal_name": partner.legal_name,
            }
        )
    for field, value in values.items():
        setattr(document, field, value)
    await session.commit()
    return await get_document(session, document_id)


async def delete_document(session: AsyncSession, document_id: UUID) -> bool:
    document = await get_document(session, document_id)
    if document is None:
        return False
    if document.status != "DRAFT":
        raise DocumentNotEditableError("only DRAFT documents can be deleted")
    await session.delete(document)
    await session.commit()
    return True
