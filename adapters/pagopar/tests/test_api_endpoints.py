"""
End-to-End API endpoint integration tests for Pagopar Adapter.
Covers Säule 4 (Observability), Routing, Auth, and Idempotency Headers.
"""

import httpx
import pytest
from pagopar.client import PagoparClient
from pagopar.models import OrderStatus


@pytest.fixture
def order_payload():
    return {
        "order_id": "ORD-API-2026-001",
        "monto_total": 450000.0,
        "descripcion_resumen": "Suscripcion Anual VibeCore ERP",
        "fecha_maxima_pago": "2026-12-31 23:59:59",
        "comprador": {
            "ruc": "4445556-7",
            "email": "contabilidad@cliente.com.py",
            "nombre": "Esteban Martinez",
            "telefono": "0971987654",
            "direccion": "Boggiani 1234, Asuncion",
            "documento": "4445556",
            "tipo_documento": "CI",
            "razon_social": "Esteban Martinez Unipersonal",
        },
        "compras_items": [
            {
                "id_producto": "PLAN-YEAR-01",
                "nombre": "VibeCore Plan Anual",
                "cantidad": 1,
                "precio_total": 450000.0,
                "categoria": "99",
            }
        ],
    }


def test_health_check_endpoint(test_client):
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "pagopar-adapter"
    assert data["version"] == "1.0.0"


def test_readiness_check_endpoint(test_client):
    response = test_client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert data["database"] == "connected"
    assert data["gateway_configured"] is True


def test_create_order_endpoint_and_idempotency_header(monkeypatch, test_client, order_payload):
    expected_hash = "mocked_gateway_hash_11223344"

    async def mock_post(client_self, url, **kwargs):
        return httpx.Response(
            status_code=200,
            json={"respuesta": True, "resultado": [{"data": expected_hash}]},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    headers = {"X-Idempotency-Key": "idem-key-unique-777", "X-Correlation-ID": "corr-uuid-1"}
    response = test_client.post("/api/v1/pagopar/orders", json=order_payload, headers=headers)

    assert response.status_code == 201
    data = response.json()
    assert data["order_id"] == "ORD-API-2026-001"
    assert data["pagopar_hash"] == expected_hash
    assert data["status"] == "PENDING_PAYMENT"
    assert "https://sandbox.pagopar.com/pagos/" in data["checkout_url"]

    # Test idempotency: send again with same idempotency key
    response2 = test_client.post("/api/v1/pagopar/orders", json=order_payload, headers=headers)
    assert response2.status_code == 201
    data2 = response2.json()
    assert data2["order_id"] == data["order_id"]
    assert data2["pagopar_hash"] == data["pagopar_hash"]


def test_get_order_by_id_endpoint(monkeypatch, test_client, order_payload):
    async def mock_post(client_self, url, **kwargs):
        return httpx.Response(
            status_code=200,
            json={"respuesta": True, "resultado": [{"data": "hash_for_get"}]},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    test_client.post("/api/v1/pagopar/orders", json=order_payload)

    # Fetch existing
    get_res = test_client.get(f"/api/v1/pagopar/orders/{order_payload['order_id']}")
    assert get_res.status_code == 200
    assert get_res.json()["order_id"] == order_payload["order_id"]

    # Fetch non-existing
    not_found_res = test_client.get("/api/v1/pagopar/orders/ORD-DOES-NOT-EXIST")
    assert not_found_res.status_code == 404


def test_webhook_api_endpoint_flow(monkeypatch, test_client, order_payload, test_settings):
    async def mock_post(client_self, url, **kwargs):
        return httpx.Response(
            status_code=200,
            json={"respuesta": True, "resultado": [{"data": "hash_for_webhook_flow"}]},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    create_res = test_client.post("/api/v1/pagopar/orders", json=order_payload)
    created_hash = create_res.json()["pagopar_hash"]

    # 1. Reject invalid signature
    bad_webhook = {
        "respuesta": True,
        "resultado": [
            {
                "pagado": True,
                "hash_pedido": created_hash,
                "monto": 450000.0,
                "token": "invalid_forged_token",
            }
        ],
    }
    bad_res = test_client.post("/api/v1/pagopar/webhook", json=bad_webhook)
    assert bad_res.status_code == 403

    # 2. Accept valid signature
    valid_token = PagoparClient.compute_webhook_token(test_settings.pagopar_private_key, created_hash)
    valid_webhook = {
        "respuesta": True,
        "resultado": [
            {
                "pagado": True,
                "fecha_pago": "2026-10-15 15:30:00",
                "forma_pago": "Bancard Web",
                "hash_pedido": created_hash,
                "monto": 450000.0,
                "token": valid_token,
                "numero_comprobante": "887766",
                "identificador_pago": 778899,
            }
        ],
    }
    good_res = test_client.post("/api/v1/pagopar/webhook", json=valid_webhook)
    assert good_res.status_code == 200

    # 3. Check order is now PAID
    order_res = test_client.get(f"/api/v1/pagopar/orders/{order_payload['order_id']}")
    assert order_res.status_code == 200
    assert order_res.json()["status"] == "PAID"
    assert order_res.json()["receipt_number"] == "887766"


def test_sync_order_polling_endpoint(monkeypatch, test_client, order_payload):
    async def mock_init_post(client_self, url, **kwargs):
        if "iniciar-transaccion" in str(url):
            return httpx.Response(
                status_code=200,
                json={"respuesta": True, "resultado": [{"data": "hash_for_sync"}]},
            )
        if "traer" in str(url):
            return httpx.Response(
                status_code=200,
                json={
                    "respuesta": True,
                    "resultado": [
                        {
                            "pagado": True,
                            "forma_pago": "Aqui Pago",
                            "monto": "450000.00",
                            "numero_pedido": order_payload["order_id"],
                        }
                    ],
                },
            )
        raise ValueError(f"Unexpected url: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_init_post)

    test_client.post("/api/v1/pagopar/orders", json=order_payload)

    # Sync status
    sync_res = test_client.post(f"/api/v1/pagopar/orders/{order_payload['order_id']}/sync")
    assert sync_res.status_code == 200
    sync_data = sync_res.json()
    assert sync_data["synced"] is True
    assert sync_data["current_status"] == "PAID"

    # Verify order state is now PAID
    order_res = test_client.get(f"/api/v1/pagopar/orders/{order_payload['order_id']}")
    assert order_res.json()["status"] == "PAID"
    assert order_res.json()["payment_method"] == "Aqui Pago"
