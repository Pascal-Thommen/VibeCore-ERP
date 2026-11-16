"""Resilient REST API Client for Dolibarr ERP (Oro Ku'i / UPA Extension)."""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_DOLIBARR_API_URL = "http://localhost:8090/api/index.php"
DEFAULT_DOLIBARR_API_KEY = "orokui-dolibarr-api-key-2026"
DEFAULT_TIMEOUT_SECONDS = 10.0


class DolibarrError(Exception):
    """Base exception for Dolibarr REST API errors."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "DOLIBARR_ERROR",
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error_code": self.error_code,
            "status_code": self.status_code,
            "message": self.message,
            "details": self.details,
        }


class DolibarrAuthError(DolibarrError):
    """Raised when the Dolibarr API token (DOLAPIKEY) is invalid or unauthorized."""

    def __init__(
        self,
        message: str = "Invalid or unauthorized Dolibarr API key (DOLAPIKEY).",
        *,
        status_code: int = 401,
        details: Any = None,
    ) -> None:
        super().__init__(
            message,
            error_code="AUTH_ERROR",
            status_code=status_code,
            details=details,
        )


class DolibarrTimeoutError(DolibarrError):
    """Raised when a Dolibarr REST API or database request times out."""

    def __init__(
        self,
        message: str = "Request to Dolibarr REST API timed out.",
        *,
        details: Any = None,
    ) -> None:
        super().__init__(
            message,
            error_code="TIMEOUT_ERROR",
            status_code=504,
            details=details,
        )


class DolibarrConnectionError(DolibarrError):
    """Raised when the Dolibarr REST API endpoint cannot be reached."""

    def __init__(
        self,
        message: str = "Unable to connect to Dolibarr REST API.",
        *,
        details: Any = None,
    ) -> None:
        super().__init__(
            message,
            error_code="CONNECTION_ERROR",
            status_code=503,
            details=details,
        )


class DolibarrAPIError(DolibarrError):
    """Raised when Dolibarr returns a 4xx/5xx application error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        details: Any = None,
    ) -> None:
        super().__init__(
            message,
            error_code="API_ERROR",
            status_code=status_code,
            details=details,
        )


class DolibarrClient:
    """Synchronous HTTP client for querying and controlling Dolibarr REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        resolved_url = (
            base_url
            if base_url is not None
            else os.environ.get("DOLIBARR_API_URL", DEFAULT_DOLIBARR_API_URL)
        )
        self.base_url = resolved_url.rstrip("/")
        self.api_key = (
            api_key
            if api_key is not None
            else os.environ.get("DOLIBARR_API_KEY", DEFAULT_DOLIBARR_API_KEY)
        )
        raw_timeout = (
            timeout
            if timeout is not None
            else float(os.environ.get("DOLIBARR_API_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)))
        )
        if raw_timeout <= 0:
            raise ValueError("timeout must be positive")
        self.timeout = raw_timeout
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        return {
            "DOLAPIKEY": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | list[Any] | None = None,
        allow_404_empty: bool = False,
    ) -> Any:
        if not self.api_key or not self.api_key.strip():
            raise DolibarrAuthError("Missing Dolibarr API key (DOLAPIKEY is empty).")

        normalized_path = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url}{normalized_path}"

        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.request(
                    method=method.upper(),
                    url=url,
                    headers=self._headers(),
                    params=params,
                    json=json_body,
                    timeout=self.timeout,
                )
        except httpx.TimeoutException as exc:
            raise DolibarrTimeoutError(
                f"Dolibarr API request timed out after {self.timeout}s: {method.upper()} {normalized_path}",
                details={"path": normalized_path, "timeout_seconds": self.timeout},
            ) from exc
        except httpx.RequestError as exc:
            raise DolibarrConnectionError(
                f"Connection to Dolibarr API failed for {method.upper()} {normalized_path}: {exc}",
                details={"path": normalized_path, "error": str(exc)},
            ) from exc

        status = response.status_code
        payload: Any = None
        if response.content:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text

        if status in (401, 403):
            err_msg = self._extract_error_message(payload) or "Unauthorized API token (DOLAPIKEY)."
            raise DolibarrAuthError(
                f"Authentication failed ({status}): {err_msg}",
                status_code=status,
                details=payload,
            )

        if status == 404 and allow_404_empty:
            return []

        if status >= 400:
            err_msg = self._extract_error_message(payload) or f"HTTP {status} error"
            raise DolibarrAPIError(
                f"Dolibarr API error ({status}) on {method.upper()} {normalized_path}: {err_msg}",
                status_code=status,
                details=payload,
            )

        return payload

    @staticmethod
    def _extract_error_message(payload: Any) -> str:
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                msg = err.get("message") or err.get("code")
                if msg:
                    return str(msg)
            if isinstance(err, str):
                return err
            if "message" in payload:
                return str(payload["message"])
        if isinstance(payload, str):
            return payload.strip()[:300]
        return ""

    # -------------------------------------------------------------------------
    # High-level Structured Domain Operations
    # -------------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        data = self.request("GET", "/status")
        success = data.get("success", {}) if isinstance(data, dict) else {}
        return {
            "ok": True,
            "api_url": self.base_url,
            "dolibarr_version": success.get("dolibarr_version", "unknown"),
            "access_locked": str(success.get("access_locked", "0")) == "1",
        }

    def list_thirdparties(
        self,
        *,
        mode: str = "all",
        limit: int = 50,
        search: str = "",
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": max(1, min(limit, 200)), "sortfield": "t.rowid", "sortorder": "ASC"}
        mode_norm = mode.strip().lower()
        if mode_norm in ("customer", "customers", "client", "clients", "1"):
            params["mode"] = 1
        elif mode_norm in ("supplier", "suppliers", "fournisseur", "vendor", "4"):
            params["mode"] = 4

        items = self.request("GET", "/thirdparties", params=params, allow_404_empty=True)
        if not isinstance(items, list):
            return []

        results: list[dict[str, Any]] = []
        q = search.strip().lower()
        for row in items:
            if not isinstance(row, dict):
                continue
            item = self._format_thirdparty(row)
            if q and not any(
                q in str(item.get(field, "")).lower()
                for field in ("name", "name_alias", "code_client", "code_supplier", "ruc", "town", "email")
            ):
                continue
            results.append(item)
        return results

    def get_thirdparty(self, thirdparty_id: int) -> dict[str, Any]:
        row = self.request("GET", f"/thirdparties/{int(thirdparty_id)}")
        if not isinstance(row, dict):
            raise DolibarrAPIError(f"Unexpected thirdparty payload for id={thirdparty_id}", status_code=500)
        return self._format_thirdparty(row)

    def create_thirdparty(
        self,
        *,
        name: str,
        is_customer: bool = True,
        is_supplier: bool = False,
        ruc: str = "",
        email: str = "",
        phone: str = "",
        town: str = "Asuncion",
        address: str = "",
        code_client: str = "auto",
        code_supplier: str = "auto",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "name": name,
            "client": "1" if is_customer else "0",
            "fournisseur": "1" if is_supplier else "0",
            "status": "1",
            "town": town,
            "address": address,
            "email": email,
            "phone": phone,
            "idprof1": ruc,
            "currency_code": "PYG",
        }
        if is_customer:
            body["code_client"] = code_client if code_client != "auto" else "-1"
        if is_supplier:
            body["code_fournisseur"] = code_supplier if code_supplier != "auto" else "-1"

        created_id = self.request("POST", "/thirdparties", json_body=body)
        tp_id = int(created_id)
        return self.get_thirdparty(tp_id)

    @staticmethod
    def _format_thirdparty(row: dict[str, Any]) -> dict[str, Any]:
        is_client = str(row.get("client", "0")) in ("1", "2", "3")
        is_supplier = str(row.get("fournisseur", "0")) == "1"
        return {
            "id": int(row.get("id", 0)),
            "name": row.get("name") or row.get("nom") or "",
            "name_alias": row.get("name_alias") or "",
            "is_customer": is_client,
            "is_supplier": is_supplier,
            "code_client": row.get("code_client") or "",
            "code_supplier": row.get("code_fournisseur") or "",
            "ruc": row.get("idprof1") or row.get("tva_intra") or "",
            "email": row.get("email") or "",
            "phone": row.get("phone") or "",
            "town": row.get("town") or "",
            "address": row.get("address") or "",
            "status": int(row.get("status", 1)),
        }

    def list_contacts(self, *, limit: int = 50) -> list[dict[str, Any]]:
        items = self.request(
            "GET",
            "/contacts",
            params={"limit": max(1, min(limit, 200)), "sortfield": "t.rowid", "sortorder": "ASC"},
            allow_404_empty=True,
        )
        if not isinstance(items, list):
            return []
        return [
            {
                "id": int(c.get("id", 0)),
                "firstname": c.get("firstname") or "",
                "lastname": c.get("lastname") or "",
                "fullname": f"{c.get('firstname') or ''} {c.get('lastname') or ''}".strip(),
                "role": c.get("poste") or "",
                "thirdparty_id": int(c.get("socid") or 0),
                "company_name": c.get("socname") or "",
                "email": c.get("email") or "",
                "phone": c.get("phone_pro") or c.get("phone_mobile") or "",
                "town": c.get("town") or "",
            }
            for c in items
            if isinstance(c, dict)
        ]

    def list_products(self, *, limit: int = 50, search: str = "") -> list[dict[str, Any]]:
        items = self.request(
            "GET",
            "/products",
            params={"limit": max(1, min(limit, 200)), "sortfield": "t.rowid", "sortorder": "ASC"},
            allow_404_empty=True,
        )
        if not isinstance(items, list):
            return []

        q = search.strip().lower()
        results: list[dict[str, Any]] = []
        for p in items:
            if not isinstance(p, dict):
                continue
            formatted = {
                "id": int(p.get("id", 0)),
                "ref": p.get("ref") or "",
                "label": p.get("label") or "",
                "type": "service" if str(p.get("type", "0")) == "1" else "product",
                "price_ht_pyg": float(p.get("price") or 0.0),
                "cost_price_pyg": float(p.get("cost_price") or p.get("pmp") or 0.0),
                "vat_rate": float(p.get("tva_tx") or 0.0),
                "stock_real": float(p.get("stock_reel") or 0.0),
                "stock_alert_threshold": float(p.get("seuil_stock_alerte") or 0.0),
                "desired_stock": float(p.get("desiredstock") or 0.0),
                "batch_tracked": str(p.get("status_batch", "0")) == "1",
            }
            if q and not any(q in str(formatted.get(k, "")).lower() for k in ("ref", "label")):
                continue
            results.append(formatted)
        return results

    def get_product_stock(self, product_id: int) -> dict[str, Any]:
        prod = self.request("GET", f"/products/{int(product_id)}")
        stock_data = self.request("GET", f"/products/{int(product_id)}/stock", allow_404_empty=True)

        warehouses_out: list[dict[str, Any]] = []
        if isinstance(stock_data, dict):
            wh_map = stock_data.get("stock_warehouses") or {}
            if isinstance(wh_map, dict):
                for wh_id, wh_info in wh_map.items():
                    if not isinstance(wh_info, dict):
                        continue
                    batches_out: list[dict[str, Any]] = []
                    detail_batch = wh_info.get("detail_batch")
                    if isinstance(detail_batch, dict):
                        for lot_code, lot_info in detail_batch.items():
                            if isinstance(lot_info, dict):
                                batches_out.append(
                                    {
                                        "batch": str(lot_info.get("batch") or lot_code),
                                        "qty": float(lot_info.get("qty") or 0.0),
                                        "sellby_timestamp": lot_info.get("sellby"),
                                    }
                                )
                    warehouses_out.append(
                        {
                            "warehouse_id": int(wh_id),
                            "real_qty": float(wh_info.get("real") or 0.0),
                            "batches": batches_out,
                        }
                    )

        return {
            "product_id": int(prod.get("id", product_id)) if isinstance(prod, dict) else int(product_id),
            "ref": prod.get("ref", "") if isinstance(prod, dict) else "",
            "label": prod.get("label", "") if isinstance(prod, dict) else "",
            "batch_tracked": str(prod.get("status_batch", "0")) == "1" if isinstance(prod, dict) else False,
            "stock_real_total": float(
                (stock_data.get("stock_reel") if isinstance(stock_data, dict) else 0.0) or 0.0
            ),
            "stock_theoretical_total": float(
                (stock_data.get("stock_theorique") if isinstance(stock_data, dict) else 0.0) or 0.0
            ),
            "warehouses": warehouses_out,
        }

    def list_warehouses(self, *, limit: int = 50) -> list[dict[str, Any]]:
        items = self.request(
            "GET",
            "/warehouses",
            params={"limit": max(1, min(limit, 200)), "sortfield": "t.rowid", "sortorder": "ASC"},
            allow_404_empty=True,
        )
        if not isinstance(items, list):
            return []
        return [
            {
                "id": int(w.get("id", 0)),
                "ref": w.get("ref") or w.get("libelle") or "",
                "location": w.get("lieu") or "",
                "description": w.get("description") or "",
                "town": w.get("town") or "",
                "address": w.get("address") or "",
                "status": int(w.get("statut", 1)),
            }
            for w in items
            if isinstance(w, dict)
        ]

    def list_stock_movements(
        self,
        *,
        limit: int = 50,
        warehouse_id: int = 0,
        product_id: int = 0,
    ) -> list[dict[str, Any]]:
        items = self.request(
            "GET",
            "/stockmovements",
            params={"limit": max(1, min(limit, 200)), "sortfield": "t.rowid", "sortorder": "DESC"},
            allow_404_empty=True,
        )
        if not isinstance(items, list):
            return []

        results: list[dict[str, Any]] = []
        for m in items:
            if not isinstance(m, dict):
                continue
            w_id = int(m.get("warehouse_id") or m.get("fk_entrepot") or 0)
            p_id = int(m.get("product_id") or m.get("fk_product") or 0)
            if warehouse_id > 0 and w_id != warehouse_id:
                continue
            if product_id > 0 and p_id != product_id:
                continue
            results.append(
                {
                    "id": int(m.get("id", 0)),
                    "product_id": p_id,
                    "warehouse_id": w_id,
                    "qty": float(m.get("qty") or 0.0),
                    "price_pyg": float(m.get("price") or 0.0),
                    "label": m.get("label") or "",
                    "inventory_code": m.get("inventorycode") or "",
                    "batch": m.get("batch") or "",
                }
            )
        return results

    def create_stock_movement(
        self,
        *,
        product_id: int,
        warehouse_id: int,
        qty: float,
        movement_label: str = "MCP Stock Adjustment",
        price: float = 0.0,
        lot: str = "",
        inventory_code: str = "MCP-MOV",
    ) -> dict[str, Any]:
        if qty == 0:
            raise DolibarrAPIError("Stock movement quantity cannot be zero.", status_code=400)
        body: dict[str, Any] = {
            "product_id": int(product_id),
            "warehouse_id": int(warehouse_id),
            "qty": float(qty),
            "movementlabel": movement_label,
            "movementcode": inventory_code,
            "price": float(price),
        }
        if lot:
            body["lot"] = lot

        mov_id = self.request("POST", "/stockmovements", json_body=body)
        return {
            "ok": True,
            "movement_id": int(mov_id) if str(mov_id).isdigit() else mov_id,
            "product_id": int(product_id),
            "warehouse_id": int(warehouse_id),
            "qty": float(qty),
            "lot": lot,
        }

    def list_proposals(self, *, limit: int = 50) -> list[dict[str, Any]]:
        items = self.request(
            "GET",
            "/proposals",
            params={"limit": max(1, min(limit, 200)), "sortfield": "t.rowid", "sortorder": "ASC"},
            allow_404_empty=True,
        )
        if not isinstance(items, list):
            return []
        status_map = {0: "draft", 1: "validated_open", 2: "signed_accepted", 3: "refused", 4: "billed"}
        return [
            {
                "id": int(pr.get("id", 0)),
                "ref": pr.get("ref") or "",
                "ref_client": pr.get("ref_client") or "",
                "thirdparty_id": int(pr.get("socid") or 0),
                "status_code": int(pr.get("statut") or pr.get("status") or 0),
                "status": status_map.get(int(pr.get("statut") or pr.get("status") or 0), "unknown"),
                "total_ht_pyg": float(pr.get("total_ht") or 0.0),
                "total_ttc_pyg": float(pr.get("total_ttc") or 0.0),
                "line_count": len(pr.get("lines") or []),
            }
            for pr in items
            if isinstance(pr, dict)
        ]

    def list_orders(self, *, limit: int = 50) -> list[dict[str, Any]]:
        items = self.request(
            "GET",
            "/orders",
            params={"limit": max(1, min(limit, 200)), "sortfield": "t.rowid", "sortorder": "ASC"},
            allow_404_empty=True,
        )
        if not isinstance(items, list):
            return []
        status_map = {-1: "cancelled", 0: "draft", 1: "validated", 2: "in_process", 3: "delivered"}
        return [
            {
                "id": int(o.get("id", 0)),
                "ref": o.get("ref") or "",
                "ref_client": o.get("ref_client") or "",
                "thirdparty_id": int(o.get("socid") or 0),
                "status_code": int(o.get("statut") or o.get("status") or 0),
                "status": status_map.get(int(o.get("statut") or o.get("status") or 0), "unknown"),
                "billed": str(o.get("billed", "0")) == "1",
                "total_ht_pyg": float(o.get("total_ht") or 0.0),
                "total_ttc_pyg": float(o.get("total_ttc") or 0.0),
                "line_count": len(o.get("lines") or []),
            }
            for o in items
            if isinstance(o, dict)
        ]

    def list_invoices(self, *, limit: int = 50, status: str = "") -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": max(1, min(limit, 200)), "sortfield": "t.rowid", "sortorder": "ASC"}
        if status.strip().lower() in ("draft", "unpaid", "paid", "cancelled"):
            params["status"] = status.strip().lower()

        items = self.request("GET", "/invoices", params=params, allow_404_empty=True)
        if not isinstance(items, list):
            return []
        return [self._format_invoice(inv) for inv in items if isinstance(inv, dict)]

    def get_invoice(self, invoice_id: int) -> dict[str, Any]:
        inv = self.request("GET", f"/invoices/{int(invoice_id)}")
        if not isinstance(inv, dict):
            raise DolibarrAPIError(f"Unexpected invoice payload for id={invoice_id}", status_code=500)
        formatted = self._format_invoice(inv)
        lines = inv.get("lines") or []
        formatted["lines"] = [
            {
                "id": int(ln.get("id", 0)),
                "product_id": int(ln.get("fk_product") or 0),
                "product_ref": ln.get("product_ref") or ln.get("ref") or "",
                "description": ln.get("desc") or ln.get("description") or ln.get("product_label") or "",
                "qty": float(ln.get("qty") or 0.0),
                "unit_price_ht_pyg": float(ln.get("subprice") or 0.0),
                "vat_rate": float(ln.get("tva_tx") or 0.0),
                "total_ht_pyg": float(ln.get("total_ht") or 0.0),
                "total_ttc_pyg": float(ln.get("total_ttc") or 0.0),
            }
            for ln in lines
            if isinstance(ln, dict)
        ]
        return formatted

    @staticmethod
    def _format_invoice(inv: dict[str, Any]) -> dict[str, Any]:
        total_ttc = float(inv.get("total_ttc") or 0.0)
        total_paid = float(inv.get("totalpaid") or 0.0)
        paid_flag = str(inv.get("paye", "0")) == "1"
        return {
            "id": int(inv.get("id", 0)),
            "ref": inv.get("ref") or "",
            "ref_client": inv.get("ref_client") or "",
            "thirdparty_id": int(inv.get("socid") or 0),
            "is_pos": (inv.get("module_source") or "") == "takepos",
            "pos_terminal": inv.get("pos_source") or "",
            "paid": paid_flag,
            "payment_state": "paid" if paid_flag else ("partial" if total_paid > 0 else "unpaid"),
            "total_ht_pyg": float(inv.get("total_ht") or 0.0),
            "total_vat_pyg": float(inv.get("total_tva") or 0.0),
            "total_ttc_pyg": total_ttc,
            "total_paid_pyg": total_paid,
            "remaining_unpaid_pyg": max(0.0, round(total_ttc - total_paid, 2)),
            "line_count": len(inv.get("lines") or []),
        }

    def list_supplier_orders(self, *, limit: int = 50) -> list[dict[str, Any]]:
        items = self.request(
            "GET",
            "/supplierorders",
            params={"limit": max(1, min(limit, 200)), "sortfield": "t.rowid", "sortorder": "ASC"},
            allow_404_empty=True,
        )
        if not isinstance(items, list):
            return []
        return [
            {
                "id": int(so.get("id", 0)),
                "ref": so.get("ref") or "",
                "ref_supplier": so.get("ref_supplier") or "",
                "supplier_id": int(so.get("socid") or 0),
                "status_code": int(so.get("statut") or so.get("status") or 0),
                "total_ht_pyg": float(so.get("total_ht") or 0.0),
                "total_ttc_pyg": float(so.get("total_ttc") or 0.0),
            }
            for so in items
            if isinstance(so, dict)
        ]

    def list_supplier_invoices(self, *, limit: int = 50) -> list[dict[str, Any]]:
        items = self.request(
            "GET",
            "/supplierinvoices",
            params={"limit": max(1, min(limit, 200)), "sortfield": "t.rowid", "sortorder": "ASC"},
            allow_404_empty=True,
        )
        if not isinstance(items, list):
            return []
        return [
            {
                "id": int(si.get("id", 0)),
                "ref": si.get("ref") or "",
                "ref_supplier": si.get("ref_supplier") or "",
                "label": si.get("label") or "",
                "supplier_id": int(si.get("socid") or 0),
                "paid": str(si.get("paye", "0")) == "1",
                "total_ht_pyg": float(si.get("total_ht") or 0.0),
                "total_ttc_pyg": float(si.get("total_ttc") or 0.0),
            }
            for si in items
            if isinstance(si, dict)
        ]

    def list_bank_accounts(self) -> list[dict[str, Any]]:
        items = self.request("GET", "/bankaccounts", params={"limit": 50}, allow_404_empty=True)
        if not isinstance(items, list):
            return []
        accounts: list[dict[str, Any]] = []
        for acc in items:
            if not isinstance(acc, dict):
                continue
            acc_id = int(acc.get("id", 0))
            lines = self.list_bank_transactions(acc_id)
            balance = sum(float(line.get("amount_pyg", 0.0)) for line in lines)
            accounts.append(
                {
                    "id": acc_id,
                    "ref": acc.get("ref") or "",
                    "label": acc.get("label") or "",
                    "currency": acc.get("currency_code") or "PYG",
                    "transaction_count": len(lines),
                    "balance_pyg": round(balance, 2),
                }
            )
        return accounts

    def list_bank_transactions(self, account_id: int) -> list[dict[str, Any]]:
        lines = self.request(
            "GET",
            f"/bankaccounts/{int(account_id)}/lines",
            allow_404_empty=True,
        )
        if not isinstance(lines, list):
            return []
        return [
            {
                "id": int(ln.get("id", 0)),
                "label": ln.get("label") or "",
                "amount_pyg": float(ln.get("amount") or 0.0),
                "payment_type": ln.get("type") or ln.get("fk_type") or "",
                "reference_num": ln.get("num_chq") or "",
                "date_operation": ln.get("dateo") or ln.get("datev") or "",
            }
            for ln in lines
            if isinstance(ln, dict)
        ]

    def list_boms_and_mos(self) -> dict[str, Any]:
        boms = self.request("GET", "/boms", params={"limit": 50}, allow_404_empty=True)
        mos = self.request("GET", "/mos", params={"limit": 50}, allow_404_empty=True)
        return {
            "boms": [
                {
                    "id": int(b.get("id", 0)),
                    "ref": b.get("ref") or "",
                    "label": b.get("label") or "",
                    "product_id": int(b.get("fk_product") or 0),
                    "qty": float(b.get("qty") or 0.0),
                    "status": int(b.get("status") or 0),
                }
                for b in (boms if isinstance(boms, list) else [])
                if isinstance(b, dict)
            ],
            "manufacturing_orders": [
                {
                    "id": int(m.get("id", 0)),
                    "ref": m.get("ref") or "",
                    "label": m.get("label") or "",
                    "product_id": int(m.get("fk_product") or 0),
                    "bom_id": int(m.get("fk_bom") or 0),
                    "qty": float(m.get("qty") or 0.0),
                    "warehouse_id": int(m.get("fk_warehouse") or 0),
                    "status": int(m.get("status") or 0),
                }
                for m in (mos if isinstance(mos, list) else [])
                if isinstance(m, dict)
            ],
        }

    def get_erp_summary(self) -> dict[str, Any]:
        status_info = self.get_status()
        thirdparties = self.list_thirdparties(limit=200)
        contacts = self.list_contacts(limit=200)
        products = self.list_products(limit=200)
        warehouses = self.list_warehouses(limit=200)
        stock_movements = self.list_stock_movements(limit=200)
        proposals = self.list_proposals(limit=200)
        orders = self.list_orders(limit=200)
        invoices = self.list_invoices(limit=200)
        supplier_orders = self.list_supplier_orders(limit=200)
        supplier_invoices = self.list_supplier_invoices(limit=200)
        bank_accounts = self.list_bank_accounts()
        mrp = self.list_boms_and_mos()

        customers = [tp for tp in thirdparties if tp["is_customer"]]
        suppliers = [tp for tp in thirdparties if tp["is_supplier"]]
        pos_invoices = [inv for inv in invoices if inv["is_pos"]]

        return {
            "ok": True,
            "dolibarr_version": status_info["dolibarr_version"],
            "api_url": self.base_url,
            "counts": {
                "thirdparties_total": len(thirdparties),
                "customers": len(customers),
                "suppliers": len(suppliers),
                "contacts": len(contacts),
                "products_and_services": len(products),
                "warehouses": len(warehouses),
                "stock_movements": len(stock_movements),
                "proposals": len(proposals),
                "customer_orders": len(orders),
                "customer_invoices_total": len(invoices),
                "pos_receipts": len(pos_invoices),
                "supplier_orders": len(supplier_orders),
                "supplier_invoices": len(supplier_invoices),
                "bank_and_cash_accounts": len(bank_accounts),
                "boms": len(mrp["boms"]),
                "manufacturing_orders": len(mrp["manufacturing_orders"]),
            },
            "financial_totals_pyg": {
                "invoiced_ttc_pyg": round(sum(i["total_ttc_pyg"] for i in invoices), 2),
                "collected_pyg": round(sum(i["total_paid_pyg"] for i in invoices), 2),
                "open_receivables_pyg": round(sum(i["remaining_unpaid_pyg"] for i in invoices), 2),
                "cash_and_bank_balances": {
                    acc["ref"]: acc["balance_pyg"] for acc in bank_accounts if acc["ref"]
                },
            },
        }
