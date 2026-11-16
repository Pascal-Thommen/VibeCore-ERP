"""FastMCP Server for Dolibarr ERP (Oro Ku'i / UPA Extension).

Hard-wired defaults:
- REST API Base URL: http://localhost:8090/api/index.php
- REST API Key (DOLAPIKEY): orokui-dolibarr-api-key-2026
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from dolibarr_mcp.client import (
    DEFAULT_DOLIBARR_API_KEY,
    DEFAULT_DOLIBARR_API_URL,
    DEFAULT_TIMEOUT_SECONDS,
    DolibarrClient,
    DolibarrError,
)

mcp = FastMCP(
    "orokui-dolibarr-mcp",
    instructions=(
        "Lokaler Dolibarr ERP MCP-Server fuer Oro Ku'i (UPA Extension). "
        "Bietet strukturierte Abfrage- und Steuerungswerkzeuge fuer Kontakte (Kunden & Lieferanten), "
        "Produkte, Lagerbestaende, Chargen/Lots, Angebote, Auftraege, Rechnungen, TakePOS-Belege, "
        "Stuecklisten (BOM), Fertigungsauftraege (MRP) sowie Kassen- und Bankbuchungen in PYG."
    ),
)

_ACTIVE_CLIENT: DolibarrClient | None = None


def get_client() -> DolibarrClient:
    """Return the configured DolibarrClient instance."""
    global _ACTIVE_CLIENT
    if _ACTIVE_CLIENT is None:
        _ACTIVE_CLIENT = DolibarrClient()
    return _ACTIVE_CLIENT


def set_client(client: DolibarrClient | None) -> None:
    """Override the active DolibarrClient instance (e.g. for custom CLI or tests)."""
    global _ACTIVE_CLIENT
    _ACTIVE_CLIENT = client


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request: Request) -> JSONResponse:
    """Health check endpoint verifying Dolibarr REST API connectivity."""
    try:
        status = get_client().get_status()
        return JSONResponse({"status": "healthy", "dolibarr": status}, status_code=200)
    except DolibarrError as exc:
        return JSONResponse(exc.to_dict(), status_code=exc.status_code or 503)


@mcp.tool()
def dolibarr_status() -> dict[str, Any]:
    """Prueft den Verbindungsstatus und die Version der lokalen Dolibarr-Instanz."""
    try:
        return get_client().get_status()
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def dolibarr_erp_summary() -> dict[str, Any]:
    """Liefert eine Gesamtzusammenfassung aller aktiven Dolibarr-Module, Belegzahlen und Salden in PYG."""
    try:
        return get_client().get_erp_summary()
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def list_thirdparties(
    mode: str = "all",
    limit: int = 50,
    search: str = "",
) -> dict[str, Any]:
    """Listet Geschaeftspartner (Dritte) auf. mode: 'all', 'customers' oder 'suppliers'."""
    try:
        items = get_client().list_thirdparties(mode=mode, limit=limit, search=search)
        return {"ok": True, "count": len(items), "thirdparties": items}
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def get_thirdparty(thirdparty_id: int) -> dict[str, Any]:
    """Ruft die Stammdaten eines Kunden oder Lieferanten anhand seiner ID ab."""
    try:
        tp = get_client().get_thirdparty(thirdparty_id)
        return {"ok": True, "thirdparty": tp}
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def create_thirdparty(
    name: str,
    is_customer: bool = True,
    is_supplier: bool = False,
    ruc: str = "",
    email: str = "",
    phone: str = "",
    town: str = "Asuncion",
    address: str = "",
) -> dict[str, Any]:
    """Legt einen neuen Kunden und/oder Lieferanten (inkl. RUC) in Dolibarr an."""
    try:
        created = get_client().create_thirdparty(
            name=name,
            is_customer=is_customer,
            is_supplier=is_supplier,
            ruc=ruc,
            email=email,
            phone=phone,
            town=town,
            address=address,
        )
        return {"ok": True, "thirdparty": created}
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def list_contacts(limit: int = 50) -> dict[str, Any]:
    """Listet Kontaktpersonen (Ansprechpartner bei Kunden und Lieferanten) auf."""
    try:
        contacts = get_client().list_contacts(limit=limit)
        return {"ok": True, "count": len(contacts), "contacts": contacts}
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def list_products(limit: int = 50, search: str = "") -> dict[str, Any]:
    """Listet Produkte und Dienstleistungen inklusive Verkaufspreis (PYG), Lagerbestand und Chargenpflicht auf."""
    try:
        products = get_client().list_products(limit=limit, search=search)
        return {"ok": True, "count": len(products), "products": products}
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def get_product_stock(product_id: int) -> dict[str, Any]:
    """Liefert den detaillierten Lagerbestand und die Chargen-/Lot-Bestände eines Produkts je Lager."""
    try:
        stock = get_client().get_product_stock(product_id)
        return {"ok": True, "stock": stock}
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def list_warehouses(limit: int = 50) -> dict[str, Any]:
    """Listet alle Dolibarr-Lagerorte (z. B. ALMACEN-OROKUI-01, ALMACEN-PROD-02, ALMACEN-TIENDA-03) auf."""
    try:
        warehouses = get_client().list_warehouses(limit=limit)
        return {"ok": True, "count": len(warehouses), "warehouses": warehouses}
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def list_stock_movements(
    limit: int = 50,
    warehouse_id: int = 0,
    product_id: int = 0,
) -> dict[str, Any]:
    """Listet reale Lagerbewegungen und Chargenbuchungen auf."""
    try:
        movements = get_client().list_stock_movements(
            limit=limit,
            warehouse_id=warehouse_id,
            product_id=product_id,
        )
        return {"ok": True, "count": len(movements), "stock_movements": movements}
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def create_stock_movement(
    product_id: int,
    warehouse_id: int,
    qty: float,
    movement_label: str = "MCP Stock Adjustment",
    price: float = 0.0,
    lot: str = "",
) -> dict[str, Any]:
    """Bucht eine reale Lagerbewegung (positiv = Zugang, negativ = Abgang) fuer ein Produkt und Lager."""
    try:
        return get_client().create_stock_movement(
            product_id=product_id,
            warehouse_id=warehouse_id,
            qty=qty,
            movement_label=movement_label,
            price=price,
            lot=lot,
        )
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def list_proposals(limit: int = 50) -> dict[str, Any]:
    """Listet Kundenangebote (Propal) mit Status und Betraegen in PYG auf."""
    try:
        proposals = get_client().list_proposals(limit=limit)
        return {"ok": True, "count": len(proposals), "proposals": proposals}
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def list_orders(limit: int = 50) -> dict[str, Any]:
    """Listet Kundenauftraege (Commande) mit Status und Betraegen in PYG auf."""
    try:
        orders = get_client().list_orders(limit=limit)
        return {"ok": True, "count": len(orders), "orders": orders}
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def list_invoices(limit: int = 50, status: str = "") -> dict[str, Any]:
    """Listet Kundenrechnungen und TakePOS-Kassenbelege (status: '', 'paid', 'unpaid', 'draft') auf."""
    try:
        invoices = get_client().list_invoices(limit=limit, status=status)
        return {"ok": True, "count": len(invoices), "invoices": invoices}
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def get_invoice(invoice_id: int) -> dict[str, Any]:
    """Ruft eine einzelne Kundenrechnung inklusive aller Rechnungspositionen ab."""
    try:
        inv = get_client().get_invoice(invoice_id)
        return {"ok": True, "invoice": inv}
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def list_supplier_documents(limit: int = 50) -> dict[str, Any]:
    """Listet Lieferantenbestellungen und Lieferantenrechnungen (Einkauf) auf."""
    try:
        client = get_client()
        s_orders = client.list_supplier_orders(limit=limit)
        s_invoices = client.list_supplier_invoices(limit=limit)
        return {
            "ok": True,
            "supplier_orders_count": len(s_orders),
            "supplier_orders": s_orders,
            "supplier_invoices_count": len(s_invoices),
            "supplier_invoices": s_invoices,
        }
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def list_cash_and_bank_ledger(account_id: int = 0) -> dict[str, Any]:
    """Listet Kassen- und Bankkonten (CAJA-POS-PYG, BANCO-OP-PYG) sowie deren Buchungszeilen in PYG auf."""
    try:
        client = get_client()
        accounts = client.list_bank_accounts()
        transactions: dict[str, list[dict[str, Any]]] = {}
        for acc in accounts:
            aid = int(acc["id"])
            if account_id > 0 and aid != account_id:
                continue
            transactions[acc["ref"] or str(aid)] = client.list_bank_transactions(aid)
        return {
            "ok": True,
            "accounts": accounts,
            "transactions_by_account": transactions,
        }
    except DolibarrError as exc:
        return exc.to_dict()


@mcp.tool()
def list_boms_and_manufacturing_orders() -> dict[str, Any]:
    """Listet Stuecklisten (BOM) und MRP-Fertigungsauftraege fuer Oro Ku'i auf."""
    try:
        data = get_client().list_boms_and_mos()
        return {"ok": True, **data}
    except DolibarrError as exc:
        return exc.to_dict()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Oro Ku'i Dolibarr ERP Model Context Protocol (MCP) Server"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport protocol (default: stdio for Claude Desktop & Cursor)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host when running with sse or streamable-http transport",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8091,
        help="Bind port when running with sse or streamable-http transport",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help=f"Override Dolibarr REST API URL (default: {DEFAULT_DOLIBARR_API_URL})",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help=f"Override Dolibarr API Key (default: {DEFAULT_DOLIBARR_API_KEY})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"HTTP request timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify connection and print ERP summary as JSON, then exit",
    )
    args = parser.parse_args(argv)

    set_client(
        DolibarrClient(
            base_url=args.api_url,
            api_key=args.api_key,
            timeout=args.timeout,
        )
    )

    if args.check:
        summary = dolibarr_erp_summary()
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0 if summary.get("ok") else 1

    if args.transport in ("sse", "streamable-http"):
        mcp.settings.host = args.host
        mcp.settings.port = args.port

    mcp.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    sys.exit(main())
