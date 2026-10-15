"""Unit and contract tests for PagoparClient (Pagopar Paraguay Payment Gateway)."""

import json

import httpx
import pytest

from vibecore.exceptions import (
    AuthenticationError,
    PaymentGatewayError,
    PaymentNotFoundError,
    PaymentTimeoutError,
)
from vibecore.payments.pagopar.client import PagoparClient
from vibecore.payments.pagopar.models import (
    BuyerModel,
    CreateOrderRequest,
    DocumentType,
    OrderItemModel,
    OrderResponse,
    OrderStatus,
    SyncOrderResponse,
)


def test_pagopar_client_health():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "healthy", "service": "pagopar-adapter"})

    with PagoparClient("http://pagopar.test", transport=httpx.MockTransport(handler)) as client:
        resp = client.health()
        assert resp["status"] == "healthy"


def test_pagopar_client_ready():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ready"
        return httpx.Response(200, json={"status": "ready", "database": True})

    with PagoparClient("http://pagopar.test", transport=httpx.MockTransport(handler)) as client:
        resp = client.ready()
        assert resp["status"] == "ready"


def test_pagopar_client_create_order():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/pagopar/orders"
        assert request.headers.get("x-adapter-key") == "test-adapter-key"
        assert request.headers.get("x-idempotency-key") == "idem-order-101"
        assert request.headers.get("x-correlation-id") == "trace-corr-101"
        body = json.loads(request.content.decode("utf-8"))
        assert body["order_id"] == "ORD-2026-001"
        assert body["monto_total"] == 150000.0
        return httpx.Response(
            201,
            json={
                "order_id": "ORD-2026-001",
                "pagopar_hash": "hash_pagopar_998877",
                "checkout_url": "https://www.pagopar.com/pagar/hash_pagopar_998877",
                "status": "INITIATED",
                "monto_total": 150000.0,
                "currency": "PYG",
                "created_at": "2026-10-15T22:00:00Z",
            },
        )

    client = PagoparClient(
        "http://pagopar.test",
        api_key="test-adapter-key",
        transport=httpx.MockTransport(handler),
    )
    req = CreateOrderRequest(
        order_id="ORD-2026-001",
        monto_total=150000.0,
        descripcion_resumen="VibeCore ERP Subscription",
        comprador=BuyerModel(
            ruc="80012345-6",
            email="pascal@vibecore.io",
            nombre="Pascal Thommen",
            telefono="0981123456",
            documento="4567890",
            tipo_documento=DocumentType.CI,
            razon_social="Pascal Thommen Einzelunternehmen",
        ),
        compras_items=[
            OrderItemModel(
                id_producto="VIBECORE-CLOUD-M",
                nombre="VibeCore Cloud Monthly",
                cantidad=1,
                precio_total=150000.0,
            )
        ],
    )
    order = client.create_order(
        req,
        idempotency_key="idem-order-101",
        correlation_id="trace-corr-101",
    )
    assert isinstance(order, OrderResponse)
    assert order.order_id == "ORD-2026-001"
    assert order.status == OrderStatus.INITIATED
    assert order.checkout_url == "https://www.pagopar.com/pagar/hash_pagopar_998877"
    client.close()


def test_pagopar_client_get_order():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/pagopar/orders/ORD-2026-001"
        return httpx.Response(
            200,
            json={
                "order_id": "ORD-2026-001",
                "pagopar_hash": "hash_123",
                "status": "PAID",
                "monto_total": 150000.0,
                "currency": "PYG",
                "created_at": "2026-10-15T22:00:00Z",
                "paid_at": "2026-10-15T22:05:00Z",
                "payment_method": "Bancard T.C.",
                "receipt_number": "REC-9988",
            },
        )

    with PagoparClient("http://pagopar.test", transport=httpx.MockTransport(handler)) as client:
        order = client.get_order("ORD-2026-001")
        assert isinstance(order, OrderResponse)
        assert order.status == OrderStatus.PAID
        assert order.receipt_number == "REC-9988"


def test_pagopar_client_get_order_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"detail": "Order ORD-MISSING not found in Pagopar adapter"}
        )

    with PagoparClient("http://pagopar.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PaymentNotFoundError) as exc_info:
            client.get_order("ORD-MISSING")
        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value)


def test_pagopar_client_sync_order():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/pagopar/orders/ORD-2026-001/sync"
        assert request.headers.get("x-correlation-id") == "corr-sync-1"
        return httpx.Response(
            200,
            json={
                "order_id": "ORD-2026-001",
                "pagopar_hash": "hash_123",
                "previous_status": "INITIATED",
                "current_status": "PAID",
                "synced": True,
                "details": "Synchronized with Pagopar upstream API",
            },
        )

    with PagoparClient("http://pagopar.test", transport=httpx.MockTransport(handler)) as client:
        sync_res = client.sync_order("ORD-2026-001", correlation_id="corr-sync-1")
        assert isinstance(sync_res, SyncOrderResponse)
        assert sync_res.current_status == OrderStatus.PAID
        assert sync_res.synced is True


def test_pagopar_client_gateway_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={"detail": "Pagopar upstream gateway returned HTTP 500 error"},
        )

    with PagoparClient("http://pagopar.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PaymentGatewayError) as exc_info:
            client.sync_order("ORD-1")
        assert exc_info.value.status_code == 502


def test_pagopar_client_gateway_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            504,
            json={"detail": "Pagopar network call timed out after 10.0s"},
        )

    with PagoparClient("http://pagopar.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PaymentTimeoutError) as exc_info:
            client.sync_order("ORD-1")
        assert exc_info.value.status_code == 504


def test_pagopar_client_unauthorized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Unauthorized adapter request"})

    with PagoparClient("http://pagopar.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AuthenticationError) as exc_info:
            client.get_order("ORD-1")
        assert exc_info.value.status_code == 401
