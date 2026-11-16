"""Integration & Resilience Tests for Dolibarr Demo Data & Local MCP Server."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_DOLIBARR_DIR = _TESTS_DIR.parent
_MCP_DIR = _DOLIBARR_DIR / "mcp"
_SCRIPTS_DIR = _DOLIBARR_DIR / "scripts"

for p in (_MCP_DIR, _SCRIPTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dolibarr_mcp.client import (  # noqa: E402
    DEFAULT_DOLIBARR_API_KEY,
    DEFAULT_DOLIBARR_API_URL,
    DolibarrAPIError,
    DolibarrAuthError,
    DolibarrClient,
    DolibarrConnectionError,
    DolibarrTimeoutError,
)
from dolibarr_mcp.server import (  # noqa: E402
    dolibarr_erp_summary,
    dolibarr_status,
    get_invoice,
    get_product_stock,
    get_thirdparty,
    list_boms_and_manufacturing_orders,
    list_cash_and_bank_ledger,
    list_contacts,
    list_invoices,
    list_orders,
    list_products,
    list_proposals,
    list_stock_movements,
    list_supplier_documents,
    list_thirdparties,
    list_warehouses,
    mcp,
    set_client,
)
from seed_demodata import verify_demodata  # noqa: E402


def _live_dolibarr_available() -> bool:
    try:
        client = DolibarrClient(timeout=3.0)
        st = client.get_status()
        return bool(st.get("ok"))
    except Exception:
        return False


LIVE_AVAILABLE = _live_dolibarr_available()


@pytest.fixture(autouse=True)
def reset_mcp_client() -> Any:
    """Ensure the default DolibarrClient is restored before and after each test."""
    set_client(DolibarrClient())
    yield
    set_client(DolibarrClient())


def test_hardwired_defaults() -> None:
    """Verify hard-wired REST API URL and API key match Oro Ku'i specifications."""
    assert DEFAULT_DOLIBARR_API_URL == "http://localhost:8090/api/index.php"
    assert DEFAULT_DOLIBARR_API_KEY == "orokui-dolibarr-api-key-2026"
    client = DolibarrClient()
    assert client.base_url == "http://localhost:8090/api/index.php"
    assert client.api_key == "orokui-dolibarr-api-key-2026"
    assert client.timeout == 10.0


def test_invalid_timeout_rejected() -> None:
    """Verify non-positive timeout values raise ValueError immediately."""
    with pytest.raises(ValueError, match="timeout must be positive"):
        DolibarrClient(timeout=0)


def test_invalid_api_token_handling_transport() -> None:
    """Verify 401/403 responses raise DolibarrAuthError and return structured AUTH_ERROR in MCP."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"code": 401, "message": "Unauthorized: Wrong value for DOLAPIKEY"}},
            request=request,
        )

    bad_client = DolibarrClient(
        api_key="invalid-token-xyz",
        timeout=5.0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DolibarrAuthError) as exc_info:
        bad_client.get_status()

    assert exc_info.value.error_code == "AUTH_ERROR"
    assert exc_info.value.status_code == 401

    set_client(bad_client)
    mcp_res = dolibarr_status()
    assert mcp_res["ok"] is False
    assert mcp_res["error_code"] == "AUTH_ERROR"
    assert mcp_res["status_code"] == 401


def test_empty_api_token_rejected() -> None:
    """Verify empty API token raises DolibarrAuthError without making network calls."""
    empty_client = DolibarrClient(api_key="   ", timeout=5.0)
    with pytest.raises(DolibarrAuthError) as exc_info:
        empty_client.get_status()
    assert exc_info.value.error_code == "AUTH_ERROR"


def test_database_and_http_timeout_handling() -> None:
    """Verify database/HTTP timeouts raise DolibarrTimeoutError and return structured TIMEOUT_ERROR."""

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Database query timed out waiting for lock", request=request)

    slow_client = DolibarrClient(
        timeout=1.5,
        transport=httpx.MockTransport(timeout_handler),
    )
    with pytest.raises(DolibarrTimeoutError) as exc_info:
        slow_client.list_products()

    assert exc_info.value.error_code == "TIMEOUT_ERROR"
    assert exc_info.value.status_code == 504

    set_client(slow_client)
    mcp_res = list_products()
    assert mcp_res["ok"] is False
    assert mcp_res["error_code"] == "TIMEOUT_ERROR"
    assert mcp_res["status_code"] == 504


def test_connection_failure_handling() -> None:
    """Verify network connection failures return structured CONNECTION_ERROR."""

    def connect_err_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    offline_client = DolibarrClient(
        timeout=2.0,
        transport=httpx.MockTransport(connect_err_handler),
    )
    with pytest.raises(DolibarrConnectionError) as exc_info:
        offline_client.get_status()

    assert exc_info.value.error_code == "CONNECTION_ERROR"
    assert exc_info.value.status_code == 503

    set_client(offline_client)
    mcp_res = dolibarr_erp_summary()
    assert mcp_res["ok"] is False
    assert mcp_res["error_code"] == "CONNECTION_ERROR"


def test_zero_qty_stock_movement_rejected() -> None:
    """Verify zero-quantity stock movement is rejected before mutating state."""
    client = DolibarrClient(timeout=5.0)
    with pytest.raises(DolibarrAPIError) as exc_info:
        client.create_stock_movement(product_id=1, warehouse_id=1, qty=0)
    assert exc_info.value.status_code == 400


@pytest.mark.skipif(not LIVE_AVAILABLE, reason="Live Dolibarr instance on port 8090 not reachable")
def test_live_invalid_api_key_against_dolibarr() -> None:
    """Verify live Dolibarr container rejects an invalid DOLAPIKEY cleanly."""
    bad_live_client = DolibarrClient(api_key="wrong-key-0000", timeout=5.0)
    with pytest.raises(DolibarrAuthError) as exc_info:
        bad_live_client.list_products()
    assert exc_info.value.status_code in (401, 403)
    assert exc_info.value.error_code == "AUTH_ERROR"


@pytest.mark.skipif(not LIVE_AVAILABLE, reason="Live Dolibarr instance on port 8090 not reachable")
def test_live_demodata_completeness_across_all_modules() -> None:
    """Verify all active Dolibarr modules contain rich, non-corrupted Oro Ku'i demo data."""
    client = DolibarrClient()
    report = verify_demodata(client)
    assert report["ok"] is True, f"Missing demo data: {report['missing_requirements']}"

    # 1. Thirdparties (Customers & Suppliers)
    customers = list_thirdparties(mode="customers")
    suppliers = list_thirdparties(mode="suppliers")
    assert customers["ok"] is True and customers["count"] >= 5
    assert suppliers["ok"] is True and suppliers["count"] >= 3
    cust_names = {c["name"] for c in customers["thirdparties"]}
    sup_names = {s["name"] for s in suppliers["thirdparties"]}
    assert "Supermercados Casa Rica S.A." in cust_names
    assert "Hotel Guarani Esplendor S.A." in cust_names
    assert "Cooperativa Agricola San Pedro Ltda." in sup_names

    first_tp = get_thirdparty(customers["thirdparties"][0]["id"])
    assert first_tp["ok"] is True
    assert first_tp["thirdparty"]["is_customer"] is True

    # 2. Contacts
    contacts = list_contacts()
    assert contacts["ok"] is True and contacts["count"] >= 6

    # 3. Products, Warehouses, Stock & Batch/Lot tracking
    warehouses = list_warehouses()
    assert warehouses["ok"] is True and warehouses["count"] >= 3
    wh_refs = {w["ref"] for w in warehouses["warehouses"]}
    assert {"ALMACEN-OROKUI-01", "ALMACEN-PROD-02", "ALMACEN-TIENDA-03"}.issubset(wh_refs)

    products = list_products()
    assert products["ok"] is True and products["count"] >= 9
    prod_by_ref = {p["ref"]: p for p in products["products"]}
    assert "OROKUI-MENGEN-01" in prod_by_ref
    assert "OROKUI-FIN-01" in prod_by_ref
    assert prod_by_ref["OROKUI-MENGEN-01"]["stock_real"] >= 400.0
    assert prod_by_ref["OROKUI-FIN-01"]["stock_real"] >= 440.0

    batch_stock = get_product_stock(prod_by_ref["OROKUI-MENGEN-01"]["id"])
    assert batch_stock["ok"] is True
    assert batch_stock["stock"]["stock_real_total"] >= 400.0
    all_batches = [
        b["batch"]
        for wh in batch_stock["stock"]["warehouses"]
        for b in wh["batches"]
    ]
    assert "LOT-2026-A01" in all_batches
    assert "LOT-2026-A02" in all_batches

    movements = list_stock_movements()
    assert movements["ok"] is True and movements["count"] >= 16

    # 4. Proposals, Orders, Invoices, TakePOS & Supplier Documents
    proposals = list_proposals()
    assert proposals["ok"] is True and proposals["count"] >= 3

    orders = list_orders()
    assert orders["ok"] is True and orders["count"] >= 3

    invoices = list_invoices()
    assert invoices["ok"] is True and invoices["count"] >= 6
    pos_invoices = [i for i in invoices["invoices"] if i["is_pos"]]
    assert len(pos_invoices) >= 2

    inv_detail = get_invoice(invoices["invoices"][0]["id"])
    assert inv_detail["ok"] is True
    assert len(inv_detail["invoice"]["lines"]) >= 1

    sup_docs = list_supplier_documents()
    assert sup_docs["ok"] is True
    assert sup_docs["supplier_orders_count"] >= 1
    assert sup_docs["supplier_invoices_count"] >= 2

    # 5. Cash & Bank Ledger (CAJA-POS-PYG & BANCO-OP-PYG)
    ledger = list_cash_and_bank_ledger()
    assert ledger["ok"] is True
    acc_by_ref = {a["ref"]: a for a in ledger["accounts"]}
    assert "CAJA-POS-PYG" in acc_by_ref
    assert "BANCO-OP-PYG" in acc_by_ref
    assert acc_by_ref["CAJA-POS-PYG"]["balance_pyg"] > 0
    assert acc_by_ref["BANCO-OP-PYG"]["balance_pyg"] > 0
    assert len(ledger["transactions_by_account"]["CAJA-POS-PYG"]) >= 4

    # 6. BOM & MRP
    mrp = list_boms_and_manufacturing_orders()
    assert mrp["ok"] is True
    assert len(mrp["boms"]) >= 1
    assert len(mrp["manufacturing_orders"]) >= 1


@pytest.mark.skipif(not LIVE_AVAILABLE, reason="Live Dolibarr instance on port 8090 not reachable")
def test_fastmcp_protocol_tool_invocation() -> None:
    """Verify FastMCP tool registration and execution via MCP call_tool interface."""

    async def _run() -> None:
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}
        expected_tools = {
            "dolibarr_status",
            "dolibarr_erp_summary",
            "list_thirdparties",
            "get_thirdparty",
            "create_thirdparty",
            "list_contacts",
            "list_products",
            "get_product_stock",
            "list_warehouses",
            "list_stock_movements",
            "create_stock_movement",
            "list_proposals",
            "list_orders",
            "list_invoices",
            "get_invoice",
            "list_supplier_documents",
            "list_cash_and_bank_ledger",
            "list_boms_and_manufacturing_orders",
        }
        assert expected_tools.issubset(tool_names)

        call_res = await mcp.call_tool("dolibarr_erp_summary", {})
        if isinstance(call_res, tuple):
            content_list, structured = call_res
            assert len(content_list) >= 1
            payload = structured if isinstance(structured, dict) else json.loads(content_list[0].text)
        else:
            assert len(call_res) >= 1
            payload = json.loads(call_res[0].text)
        assert payload["ok"] is True
        assert payload["counts"]["products_and_services"] >= 9
        assert payload["counts"]["customer_invoices_total"] >= 6

    asyncio.run(_run())
