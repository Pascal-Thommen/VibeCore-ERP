"""
Unit tests for PagoparClient HTTP transport, retries, and gateway error handling.
Säule 1 (Resilienz und Netzwerkstabilität) des Software Testing Audit Frameworks.
"""

import httpx
import pytest
from pagopar.client import (
    PagoparClient,
    PagoparGatewayError,
    PagoparNetworkTimeoutError,
)
from pagopar.models import BuyerModel, DocumentType, OrderItemModel


@pytest.fixture
def sample_buyer():
    return BuyerModel(
        ruc="80012345-6",
        email="cliente@empresa.com.py",
        nombre="Carlos Benitez",
        telefono="0981123456",
        direccion="Av. Santa Teresa, Asuncion",
        documento="80012345",
        tipo_documento=DocumentType.CI,
        razon_social="Carlos Benitez SA",
    )


@pytest.fixture
def sample_items():
    return [
        OrderItemModel(
            id_producto="SKU-001",
            nombre="ERP Subscription Pro",
            cantidad=1,
            precio_total=150000.0,
            categoria="99",
        )
    ]


@pytest.mark.asyncio
async def test_initiate_transaction_success(monkeypatch, sample_buyer, sample_items, test_settings):
    expected_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"

    async def mock_post(client_self, url, **kwargs):
        assert "/api/comercios/2.0/iniciar-transaccion" in str(url)
        payload = kwargs.get("json", {})
        assert payload["monto_total"] == 150000.0
        assert payload["id_pedido_comercio"] == "ORD-001"
        assert payload["comprador"]["email"] == "cliente@empresa.com.py"

        return httpx.Response(
            status_code=200,
            json={"respuesta": True, "resultado": [{"data": expected_hash}]},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    client = PagoparClient(test_settings)
    result = await client.initiate_transaction(
        order_id="ORD-001",
        monto_total=150000.0,
        description="Abono ERP Mensual",
        buyer=sample_buyer,
        items=sample_items,
    )

    assert result["pagopar_hash"] == expected_hash
    assert result["checkout_url"] == f"https://sandbox.pagopar.com/pagos/{expected_hash}"


@pytest.mark.asyncio
async def test_initiate_transaction_business_rejection(monkeypatch, sample_buyer, sample_items, test_settings):
    async def mock_post(client_self, url, **kwargs):
        return httpx.Response(
            status_code=200,
            json={"respuesta": False, "resultado": "El comercio no se encuentra activo"},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    client = PagoparClient(test_settings)
    with pytest.raises(PagoparGatewayError) as exc_info:
        await client.initiate_transaction(
            order_id="ORD-REJECT",
            monto_total=150000.0,
            description="Rejection Test",
            buyer=sample_buyer,
            items=sample_items,
        )
    assert "El comercio no se encuentra activo" in str(exc_info.value)


@pytest.mark.asyncio
async def test_initiate_transaction_retry_on_server_error(monkeypatch, sample_buyer, sample_items, test_settings):
    attempts = 0

    async def mock_post(client_self, url, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(status_code=502, text="Bad Gateway from Pagopar upstream")
        return httpx.Response(
            status_code=200,
            json={"respuesta": True, "resultado": [{"data": "retry_success_hash"}]},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    client = PagoparClient(test_settings)
    result = await client.initiate_transaction(
        order_id="ORD-RETRY",
        monto_total=100000.0,
        description="Retry Test",
        buyer=sample_buyer,
        items=sample_items,
    )

    assert attempts == 2
    assert result["pagopar_hash"] == "retry_success_hash"


@pytest.mark.asyncio
async def test_initiate_transaction_timeout_exhaustion(monkeypatch, sample_buyer, sample_items, test_settings):
    async def mock_post(client_self, url, **kwargs):
        raise httpx.ConnectTimeout("Connection timeout to api-sandbox.pagopar.com")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    client = PagoparClient(test_settings)
    with pytest.raises(PagoparNetworkTimeoutError):
        await client.initiate_transaction(
            order_id="ORD-TIMEOUT",
            monto_total=100000.0,
            description="Timeout Test",
            buyer=sample_buyer,
            items=sample_items,
        )


@pytest.mark.asyncio
async def test_poll_order_status_success(monkeypatch, test_settings):
    async def mock_post(client_self, url, **kwargs):
        assert "/api/pedidos/1.1/traer" in str(url)
        payload = kwargs.get("json", {})
        assert payload["token_publico"] == test_settings.pagopar_public_key
        assert payload["hash_pedido"] == "test_hash_123"

        return httpx.Response(
            status_code=200,
            json={
                "respuesta": True,
                "resultado": [
                    {
                        "pagado": True,
                        "forma_pago": "SIPAP QR",
                        "monto": "150000.00",
                        "numero_pedido": "ORD-001",
                        "fecha_pago": "2026-10-15 11:20:00",
                    }
                ],
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    client = PagoparClient(test_settings)
    poll_result = await client.poll_order_status("test_hash_123")

    assert poll_result["pagado"] is True
    assert poll_result["forma_pago"] == "SIPAP QR"
    assert poll_result["numero_pedido"] == "ORD-001"
