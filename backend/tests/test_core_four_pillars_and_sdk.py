"""
Four-Pillars Test Suite for the VibeCore Finance Core, Python SDK, and Docker Compose Stacks.

Covers:
1. Säule 1 (Resilienz & Timeouts): Database outage handling on /api/v1/ready (503),
   IntegrityError transaction rollback on write errors (409), and SDK network timeout handling.
2. Säule 2 (Datenintegrität & ACID): Full end-to-end CRUD and accounting lifecycle via CoreClient
   against the FastAPI Core API (Partners, Accounts, Taxes, Products, Documents with Ley 6380/19
   gross-inclusive IVA, and balanced Journal Entries with atomic OutboxEvent staging).
3. Säule 3 (Sicherheit & Vier-Augen-Prinzip): Prevention of AI agent approval, prevention of
   creator self-approval, rejection of inactive/non-postable accounts, and immutability of
   POSTED documents and journal entries.
4. Säule 4 (Observability, Adapter SDK & Docker Compose): Semantic payload verification across
   CoreClient and AdapterClient, plus structural validation of all Docker Compose definitions.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError

# Ensure SDK is importable in local and CI runs
REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_PATH = REPO_ROOT / "sdk"
if str(SDK_PATH) not in sys.path:
    sys.path.insert(0, str(SDK_PATH))

from vibecore import AdapterClient, CoreClient, HealthStatus  # noqa: E402

from app.db.session import get_async_session, get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Account,
    Document,
    DocumentItem,
    JournalEntry,
    JournalLine,
    OutboxEvent,
    Partner,
    Product,
    Tax,
)


class StatefulCoreAsyncSession:
    """In-memory async session preserving entity state and transaction boundaries."""

    def __init__(self) -> None:
        self.partners: dict[UUID, Partner] = {}
        self.accounts: dict[UUID, Account] = {}
        self.taxes: dict[UUID, Tax] = {}
        self.products: dict[UUID, Product] = {}
        self.documents: dict[UUID, Document] = {}
        self.journal_entries: dict[UUID, JournalEntry] = {}
        self.outbox_events: list[OutboxEvent] = []
        self.commits: int = 0
        self.rollbacks: int = 0
        self.force_integrity_error: bool = False

    def _stamp(self, entity: Any) -> None:
        now = datetime.now(UTC)
        if getattr(entity, "id", None) is None:
            entity.id = uuid4()
        if getattr(entity, "created_at", None) is None:
            entity.created_at = now
        entity.updated_at = now
        if getattr(entity, "metadata_", None) is None:
            entity.metadata_ = {}

    def add(self, entity: Any) -> None:
        if self.force_integrity_error:
            raise IntegrityError(
                "INSERT", {}, Exception("duplicate key value violates unique constraint")
            )

        self._stamp(entity)
        if isinstance(entity, Partner):
            if getattr(entity, "is_customer", None) is None:
                entity.is_customer = False
            if getattr(entity, "is_supplier", None) is None:
                entity.is_supplier = False
            if getattr(entity, "is_active", None) is None:
                entity.is_active = True
            self.partners[entity.id] = entity
        elif isinstance(entity, Account):
            if getattr(entity, "reconcile", None) is None:
                entity.reconcile = False
            if getattr(entity, "allow_posting", None) is None:
                entity.allow_posting = True
            if getattr(entity, "is_active", None) is None:
                entity.is_active = True
            self.accounts[entity.id] = entity
        elif isinstance(entity, Tax):
            if getattr(entity, "scope", None) is None:
                entity.scope = "BOTH"
            if getattr(entity, "is_active", None) is None:
                entity.is_active = True
            self.taxes[entity.id] = entity
        elif isinstance(entity, Product):
            if getattr(entity, "is_sales_item", None) is None:
                entity.is_sales_item = True
            if getattr(entity, "is_purchase_item", None) is None:
                entity.is_purchase_item = True
            if getattr(entity, "standard_price", None) is None:
                entity.standard_price = Decimal("0")
            if getattr(entity, "is_active", None) is None:
                entity.is_active = True
            self.products[entity.id] = entity
        elif isinstance(entity, Document):
            if getattr(entity, "sifen_series", None) is None:
                entity.sifen_series = ""
            if getattr(entity, "sifen_status", None) is None:
                entity.sifen_status = "NOT_SENT"
            if getattr(entity, "sifen_result", None) is None:
                entity.sifen_result = {}
            entity.items = []
            self.documents[entity.id] = entity
        elif isinstance(entity, DocumentItem):
            doc = self.documents[entity.document_id]
            doc.items.append(entity)
        elif isinstance(entity, JournalEntry):
            entity.lines = []
            self.journal_entries[entity.id] = entity
        elif isinstance(entity, JournalLine):
            entry = self.journal_entries[entity.journal_entry_id]
            entry.lines.append(entity)
        elif isinstance(entity, OutboxEvent):
            if getattr(entity, "status", None) is None:
                entity.status = "PENDING"
            self.outbox_events.append(entity)

    async def get(self, model: type, entity_id: UUID) -> Any | None:
        if model is Partner:
            return self.partners.get(entity_id)
        if model is Account:
            return self.accounts.get(entity_id)
        if model is Tax:
            return self.taxes.get(entity_id)
        if model is Product:
            return self.products.get(entity_id)
        if model is Document:
            return self.documents.get(entity_id)
        if model is JournalEntry:
            return self.journal_entries.get(entity_id)
        return None

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, entity: Any) -> None:
        entity.updated_at = datetime.now(UTC)

    async def delete(self, entity: Any) -> None:
        if isinstance(entity, Partner):
            self.partners.pop(entity.id, None)
        elif isinstance(entity, Account):
            self.accounts.pop(entity.id, None)
        elif isinstance(entity, Tax):
            self.taxes.pop(entity.id, None)
        elif isinstance(entity, Product):
            self.products.pop(entity.id, None)
        elif isinstance(entity, Document):
            self.documents.pop(entity.id, None)
        elif isinstance(entity, JournalEntry):
            self.journal_entries.pop(entity.id, None)

    async def scalars(self, statement: Any) -> Any:
        sql = str(statement)
        items: list[Any] = []
        if "core.partner" in sql:
            items = list(self.partners.values())
        elif "core.account" in sql:
            items = list(self.accounts.values())
        elif "core.tax" in sql:
            items = list(self.taxes.values())
        elif "core.product" in sql:
            items = list(self.products.values())
        elif "core.document" in sql:
            items = list(self.documents.values())
            if "WHERE core.document.id =" in sql:
                target_id = statement.whereclause.right.value
                items = [d for d in items if d.id == target_id]
        elif "core.journal_entry" in sql:
            items = list(self.journal_entries.values())
            if "WHERE core.journal_entry.id =" in sql:
                target_id = statement.whereclause.right.value
                items = [j for j in items if j.id == target_id]

        class _ScalarResult:
            def __init__(self, rows: list[Any]) -> None:
                self._rows = rows

            def __iter__(self):
                return iter(self._rows)

            def one_or_none(self) -> Any | None:
                return self._rows[0] if self._rows else None

        return _ScalarResult(items)


class _AsgiBridgeTransport(httpx.BaseTransport):
    """Bridges synchronous httpx.Client calls to FastAPI TestClient while preserving headers."""

    def __init__(self, test_client: TestClient) -> None:
        self._test_client = test_client

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        resp = self._test_client.request(
            method=request.method,
            url=str(request.url.raw_path.decode("ascii")),
            headers=dict(request.headers),
            content=request.read(),
        )
        return httpx.Response(
            status_code=resp.status_code,
            headers=dict(resp.headers),
            content=resp.content,
            request=request,
        )


@pytest.fixture
def core_env():
    session = StatefulCoreAsyncSession()

    async def _override_async_session():
        yield session

    class _HealthySyncSession:
        def execute(self, _stmt: Any) -> int:
            return 1

    def _override_sync_session():
        yield _HealthySyncSession()

    app.dependency_overrides[get_async_session] = _override_async_session
    app.dependency_overrides[get_session] = _override_sync_session

    try:
        with TestClient(app) as tc:
            transport = _AsgiBridgeTransport(tc)
            with CoreClient(
                "http://vibecore.local",
                access_token="core-test-jwt-token",
                timeout=5.0,
                transport=transport,
            ) as sdk_client:
                yield session, tc, sdk_client
    finally:
        app.dependency_overrides.clear()


def test_pillar_1_resilience_database_outage_and_integrity_rollback(core_env) -> None:
    """
    Säule 1 (Resilienz & Timeouts):
    Verifies liveness vs readiness under database failure (503 Service Unavailable),
    IntegrityError session rollback (409 Conflict without SQL leak), and SDK network timeouts.
    """
    session, tc, sdk_client = core_env

    # 1. Health & Ready succeed when DB is reachable
    assert sdk_client.health() == HealthStatus(status="ok")
    assert sdk_client.ready() == HealthStatus(status="ready")

    # 2. Simulate PostgreSQL connection failure on /api/v1/ready -> 503 Service Unavailable
    class _BrokenSyncSession:
        def execute(self, _stmt: Any) -> None:
            raise OperationalError("SELECT 1", {}, Exception("connection to server at 'db' failed"))

    def _broken_session_dep():
        yield _BrokenSyncSession()

    app.dependency_overrides[get_session] = _broken_session_dep
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        sdk_client.ready()
    assert exc_info.value.response.status_code == 503
    assert exc_info.value.response.json() == {"detail": "database is unavailable"}

    # Liveness (/api/v1/health) remains 200 OK even when PostgreSQL is down
    assert sdk_client.health() == HealthStatus(status="ok")

    # 3. Simulate IntegrityError -> session.rollback() is called, 409 returned without SQL leak
    session.force_integrity_error = True
    with pytest.raises(httpx.HTTPStatusError) as conflict_exc:
        sdk_client.create_partner(
            {
                "ruc": "80012345",
                "dv": "6",
                "legal_name": "Duplicado S.A.",
                "is_customer": True,
            }
        )
    assert conflict_exc.value.response.status_code == 409
    assert conflict_exc.value.response.json()["detail"] == (
        "operation conflicts with an existing or referenced Core record"
    )
    assert session.rollbacks == 1
    session.force_integrity_error = False

    # 4. SDK timeout enforcement when network hangs
    def _timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Core API read timed out", request=request)

    with CoreClient(
        "http://vibecore.local",
        access_token="token",
        timeout=1.5,
        transport=httpx.MockTransport(_timeout_handler),
    ) as timeout_client:
        with pytest.raises(httpx.ReadTimeout):
            timeout_client.list_accounts()


def test_pillar_2_and_3_full_core_lifecycle_acid_outbox_and_four_eyes_security(core_env) -> None:
    """
    Säule 2 (Datenintegrität & ACID) + Säule 3 (Sicherheit & Vier-Augen-Prinzip):
    Executes the complete Finance Core workflow via CoreClient SDK and verifies
    Ley 6380/19 IVA math, four-eyes human approval, immutability, and Outbox atomicity.
    """
    session, _tc, sdk = core_env

    # 1. Partner CRUD
    partner = sdk.create_partner(
        {
            "ruc": "80055544",
            "dv": "3",
            "legal_name": "Agropecuaria Guaraní S.A.",
            "trade_name": "AgroGuaraní",
            "is_customer": True,
            "is_supplier": False,
            "metadata": {"region": "Alto Paraná"},
        }
    )
    partner_id = partner["id"]
    assert partner["ruc"] == "80055544"
    assert partner["metadata"] == {"region": "Alto Paraná"}
    assert len(sdk.list_partners()) == 1

    updated_partner = sdk.update_partner(partner_id, {"trade_name": "AgroGuaraní PY"})
    assert updated_partner["trade_name"] == "AgroGuaraní PY"
    assert sdk.get_partner(partner_id)["trade_name"] == "AgroGuaraní PY"

    # 2. Chart of Accounts CRUD + self-parent security guard
    cash_account = sdk.create_account(
        {
            "code": "1.1.01.01",
            "name": "Caja y Bancos PYG",
            "account_type": "asset_current",
            "allow_posting": True,
        }
    )
    revenue_account = sdk.create_account(
        {
            "code": "4.1.01.01",
            "name": "Ventas Gravadas 10%",
            "account_type": "income",
            "allow_posting": True,
        }
    )
    header_account = sdk.create_account(
        {
            "code": "1.1.01",
            "name": "Disponibilidades (Header)",
            "account_type": "asset_current",
            "allow_posting": False,
        }
    )
    assert len(sdk.list_accounts()) == 3

    # Self-parenting an account must be rejected with 422
    with pytest.raises(httpx.HTTPStatusError) as self_parent_exc:
        sdk.update_account(cash_account["id"], {"parent_id": cash_account["id"]})
    assert self_parent_exc.value.response.status_code == 422
    assert "cannot be its own parent" in self_parent_exc.value.response.json()["detail"]

    # 3. Tax CRUD (Paraguayan Ley 6380/19 IVA 10%)
    iva_10 = sdk.create_tax(
        {
            "code": "IVA_10",
            "name": "IVA 10% Ley 6380/19",
            "rate": "10",
            "scope": "BOTH",
            "sales_account_id": revenue_account["id"],
        }
    )
    assert Decimal(iva_10["rate"]) == Decimal("10")
    assert len(sdk.list_taxes()) == 1

    # 4. Product CRUD
    product = sdk.create_product(
        {
            "sku": "SOJA-TON-01",
            "name": "Soja en Grano Exportación",
            "unit_of_measure": "TON",
            "standard_price": "2200000",
            "default_tax_id": iva_10["id"],
            "income_account_id": revenue_account["id"],
        }
    )
    assert product["sku"] == "SOJA-TON-01"
    assert len(sdk.list_products()) == 1

    # 5. Electronic Sales Document with gross-inclusive IVA 10% (2,200,000 PYG = 2M Net + 200k IVA)
    doc = sdk.create_document(
        {
            "document_type": "INVOICE",
            "direction": "SALES",
            "created_by_actor": "AI_AGENT",
            "partner_id": partner_id,
            "issued_at": "2026-10-30T14:00:00-03:00",
            "currency_code": "PYG",
            "issuer_ruc": "80099988",
            "issuer_dv": "1",
            "issuer_legal_name": "VibeCore Paraguay S.A.",
            "is_electronic": True,
            "timbrado_number": "12345678",
            "establishment_code": "001",
            "point_of_issue_code": "001",
            "sifen_document_type": "01",
            "sifen_emission_type": "1",
            "sifen_document_number": "0000001",
            "sifen_cdc": "01800999881001001000000112026103011234567890",
            "sifen_security_code": "123456789",
            "items": [
                {
                    "product_id": product["id"],
                    "tax_id": iva_10["id"],
                    "description": "Soja en Grano Exportación",
                    "unit_of_measure": "TON",
                    "quantity": "1",
                    "unit_price": "2200000",
                }
            ],
        }
    )
    assert doc["status"] == "DRAFT"
    assert Decimal(doc["subtotal"]) == Decimal("2000000")
    assert Decimal(doc["tax_total"]) == Decimal("200000")
    assert Decimal(doc["total"]) == Decimal("2200000")
    assert len(sdk.list_documents()) == 1

    # 6. Double-Entry Journal Entry Lifecycle + Four-Eyes Principle + Outbox Event
    # Attempt to post to non-postable header account must fail with 422
    with pytest.raises(httpx.HTTPStatusError) as non_postable_exc:
        sdk.create_journal_entry(
            {
                "created_by_actor": "HUMAN_CARLOS",
                "entry_date": "2026-10-30",
                "description": "Invalid header account posting",
                "currency_code": "PYG",
                "lines": [
                    {"account_id": header_account["id"], "debit": "2200000", "credit": "0"},
                    {"account_id": revenue_account["id"], "debit": "0", "credit": "2200000"},
                ],
            }
        )
    assert non_postable_exc.value.response.status_code == 422

    # Create valid balanced DRAFT journal entry
    entry = sdk.create_journal_entry(
        {
            "created_by_actor": "HUMAN_CARLOS",
            "entry_date": "2026-10-30",
            "description": "Factura Venta Soja 001-001-0000001",
            "reference": "FAC-0000001",
            "source_document_id": doc["id"],
            "currency_code": "PYG",
            "lines": [
                {"account_id": cash_account["id"], "debit": "2200000", "credit": "0"},
                {"account_id": revenue_account["id"], "debit": "0", "credit": "2200000"},
            ],
        }
    )
    entry_id = entry["id"]
    assert entry["status"] == "DRAFT"

    # Cannot post directly from DRAFT without submitting first -> 409 Conflict
    with pytest.raises(httpx.HTTPStatusError) as premature_post_exc:
        sdk.post_journal_entry(
            entry_id,
            {"approved_by_actor": "HUMAN_MARIA", "approved_by_role": "ACCOUNTANT"},
        )
    assert premature_post_exc.value.response.status_code == 409

    # Submit journal entry -> PENDING_APPROVAL
    submitted = sdk.submit_journal_entry(entry_id)
    assert submitted["status"] == "PENDING_APPROVAL"

    # Security Check 1: Creator cannot approve their own journal entry (Four-Eyes violation) -> 422
    with pytest.raises(httpx.HTTPStatusError) as self_approve_exc:
        sdk.post_journal_entry(
            entry_id,
            {"approved_by_actor": "HUMAN_CARLOS", "approved_by_role": "ACCOUNTANT"},
        )
    assert self_approve_exc.value.response.status_code == 422
    assert "creator cannot approve" in self_approve_exc.value.response.json()["detail"]

    # Security Check 2: AI_AGENT cannot approve a journal entry -> 422
    with pytest.raises(httpx.HTTPStatusError) as ai_approve_exc:
        sdk.post_journal_entry(
            entry_id,
            {"approved_by_actor": "AI_AGENT", "approved_by_role": "ADMIN"},
        )
    assert ai_approve_exc.value.response.status_code == 422

    # Valid Four-Eyes human approval posts the entry and atomically stages OutboxEvent
    assert len(session.outbox_events) == 0
    posted = sdk.post_journal_entry(
        entry_id,
        {"approved_by_actor": "HUMAN_MARIA", "approved_by_role": "ACCOUNTANT"},
    )
    assert posted["status"] == "POSTED"
    assert posted["posted_by_actor"] == "HUMAN_MARIA"
    assert posted["posted_by_role"] == "ACCOUNTANT"
    assert posted["posted_at"] is not None

    # Verify transactional OutboxEvent was atomically recorded
    assert len(session.outbox_events) == 1
    outbox_ev = session.outbox_events[0]
    assert outbox_ev.event_type == "journal_entry.posted"
    assert str(outbox_ev.aggregate_id) == entry_id
    assert outbox_ev.payload["data"]["reference"] == "FAC-0000001"
    assert outbox_ev.payload["meta"] == {}
    assert outbox_ev.payload["custom_data"] == {}

    # Immutability Check: POSTED journal entry cannot be updated or deleted -> 409 Conflict
    with pytest.raises(httpx.HTTPStatusError) as update_posted_exc:
        sdk.update_journal_entry(entry_id, {"description": "Tampered description"})
    assert update_posted_exc.value.response.status_code == 409

    with pytest.raises(httpx.HTTPStatusError) as delete_posted_exc:
        sdk.delete_journal_entry(entry_id)
    assert delete_posted_exc.value.response.status_code == 409


def test_pillar_4_adapter_sdk_semantic_payloads_and_headers() -> None:
    """
    Säule 4 (Observability & Adapter SDK):
    Verifies that AdapterClient sends authenticated headers, correlation/idempotency keys,
    and semantically valid payloads across SIFEN, Pagopar, Stripe, Mail, WhatsApp, and Storage.
    """
    recorded_requests: list[httpx.Request] = []

    def _adapter_handler(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json={"status": "healthy"})
        if path == "/ready":
            return httpx.Response(200, json={"ready": True, "database": "connected"})
        if path == "/api/v1/sifen/submit":
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                201,
                json={
                    "cdc": "01800111114001001000000222026101411234567896",
                    "dte_type": 1,
                    "status": "ACCEPTED",
                    "sifen_code": "0260",
                    "protocol_number": "9988776655",
                    "retry_count": 0,
                    "meta": body.get("meta"),
                    "custom_data": body.get("custom_data"),
                },
            )
        if path == "/api/v1/sifen/outbox/flush":
            return httpx.Response(
                200,
                json={
                    "processed_count": 1,
                    "accepted_count": 1,
                    "rejected_count": 0,
                    "still_queued_count": 0,
                    "items": [],
                },
            )
        if path == "/api/v1/pagopar/orders":
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                201,
                json={
                    "order_id": body["order_id"],
                    "pagopar_hash": "pp_hash_123",
                    "status": "PENDING_PAYMENT",
                    "checkout_url": "https://sandbox.pagopar.com/pagos/pp_hash_123",
                    "amount_pyg": body["monto_total"],
                },
            )
        if path == "/api/v1/stripe/checkout-sessions":
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                201,
                json={
                    "order_id": body["order_id"],
                    "stripe_id": "cs_test_123",
                    "status": "PENDING_PAYMENT",
                    "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_123",
                    "amount": body["amount_total"],
                    "amount_cents": int(body["amount_total"] * 100),
                    "currency": body["currency"],
                },
            )
        if path == "/api/v1/mail/send":
            return httpx.Response(
                202,
                json={
                    "message_id": "msg_01JXYZ",
                    "status": "queued",
                    "queued_at": "2026-10-30T15:00:00Z",
                },
            )
        if path == "/api/v1/otp/send":
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "reference_id": "otp_ref_01",
                    "phone_number": body["phone_number"],
                    "whatsapp_message_id": "wamid.otp_01",
                },
            )
        if path == "/api/v1/storage/presigned-upload":
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "file_id": f"docs/{body['filename']}",
                    "bucket": "vibecore-documents",
                    "upload_url": f"https://s3.vibecore.local/vibecore-documents/docs/{body['filename']}",
                    "expires_in_seconds": 3600,
                },
            )
        return httpx.Response(404, json={"detail": "not found"})

    with AdapterClient(
        "http://adapter.vibecore.local",
        api_key="adapter-secret-key",
        timeout=5.0,
        transport=httpx.MockTransport(_adapter_handler),
    ) as adapter:
        assert adapter.health() == HealthStatus(status="healthy")
        assert adapter.ready()["ready"] is True

        dte = adapter.submit_sifen_dte(
            {
                "header": {"document_number": "0000022"},
                "items": [],
                "profile": {"ruc": "80011111", "dv": "4", "obligaciones": [700]},
                "meta": {"source": "core"},
                "custom_data": {"sucursal": "001"},
            },
            idempotency_key="sifen-idem-22",
            correlation_id="corr-sifen-22",
        )
        assert dte["status"] == "ACCEPTED"
        assert dte["sifen_code"] == "0260"
        assert dte["meta"] == {"source": "core"}

        flush_res = adapter.flush_sifen_outbox(correlation_id="corr-flush-1")
        assert flush_res["accepted_count"] == 1

        pp_order = adapter.create_pagopar_order(
            {"order_id": "ORD-PP-1", "monto_total": 150000.0},
            idempotency_key="pp-idem-1",
            correlation_id="corr-pp-1",
        )
        assert pp_order["pagopar_hash"] == "pp_hash_123"

        stripe_cs = adapter.create_stripe_checkout_session(
            {"order_id": "ORD-ST-1", "amount_total": 49.99, "currency": "USD"},
            idempotency_key="st-idem-1",
        )
        assert stripe_cs["stripe_id"] == "cs_test_123"
        assert stripe_cs["amount_cents"] == 4999

        mail_res = adapter.send_mail(
            {"to": ["cliente@empresa.com.py"], "subject": "Factura Electrónica"},
            idempotency_key="mail-idem-1",
        )
        assert mail_res["status"] == "queued"

        otp_res = adapter.send_whatsapp_otp(
            {"phone_number": "+595981123456", "purpose": "login"}
        )
        assert otp_res["success"] is True

        upload_res = adapter.create_presigned_upload(
            {"filename": "factura.pdf", "content_type": "application/pdf"}
        )
        assert upload_res["bucket"] == "vibecore-documents"

    # Verify auth and traceability headers on recorded requests
    sifen_req = next(r for r in recorded_requests if r.url.path == "/api/v1/sifen/submit")
    assert sifen_req.headers["X-Adapter-Key"] == "adapter-secret-key"
    assert sifen_req.headers["Authorization"] == "Bearer adapter-secret-key"
    assert sifen_req.headers["X-Idempotency-Key"] == "sifen-idem-22"
    assert sifen_req.headers["X-Correlation-ID"] == "corr-sifen-22"


def test_pillar_4_docker_compose_stacks_are_clean_and_have_healthchecks() -> None:
    """
    Verifies that the Finance Core and all 7 Adapter Docker Compose stacks exist,
    contain no obsolete 'version:' keys or dead placeholders, and define healthchecks.
    """
    compose_files = [
        REPO_ROOT / "backend" / "docker-compose.yml",
        REPO_ROOT / "adapters" / "auth" / "docker-compose.yml",
        REPO_ROOT / "adapters" / "mail" / "docker-compose.yml",
        REPO_ROOT / "adapters" / "pagopar" / "docker-compose.yml",
        REPO_ROOT / "adapters" / "sifen" / "docker-compose.yml",
        REPO_ROOT / "adapters" / "storage" / "docker-compose.yml",
        REPO_ROOT / "adapters" / "stripe" / "docker-compose.yml",
        REPO_ROOT / "adapters" / "whatsapp" / "docker-compose.yml",
    ]

    for compose_path in compose_files:
        assert compose_path.is_file(), f"Missing Docker Compose file: {compose_path}"
        content = compose_path.read_text(encoding="utf-8")
        assert not content.lstrip().startswith("version:"), (
            f"Obsolete Compose 'version:' attribute found in {compose_path}"
        )
        assert "healthcheck:" in content, f"Missing container healthcheck in {compose_path}"
        assert "STRIPE_PUBLISHABLE_KEY" not in content, (
            f"Dead placeholder STRIPE_PUBLISHABLE_KEY found in {compose_path}"
        )

    # Ensure empty scaffold dummy folders are gone
    for removed_dir in (
        REPO_ROOT / "backend" / "core",
        REPO_ROOT / "backend" / "shell",
        REPO_ROOT / "backend" / "shared",
        REPO_ROOT / "adapters" / "sifen" / "blueprints",
    ):
        assert not removed_dir.exists(), f"Empty dummy directory still exists: {removed_dir}"
