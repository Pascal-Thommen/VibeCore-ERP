"""
Tests for ACID database guarantees, transaction rollbacks, and schema boundary validations.
Säule 2 (Datenintegrität und Transaktionen ACID) des Software Testing Audit Frameworks.
"""

import httpx
import pytest
from pagopar.client import PagoparClient, PagoparError
from pagopar.db_models import PagoparTransaction
from pagopar.models import (
    BuyerModel,
    CreateOrderRequest,
    DocumentType,
    OrderItemModel,
)
from pagopar.service import PagoparPaymentService


def test_schema_rejects_negative_or_zero_amounts(test_client):
    invalid_payload = {
        "order_id": "ORD-INVALID-AMOUNT",
        "monto_total": -500.0,
        "descripcion_resumen": "Negative amount test",
        "comprador": {
            "ruc": "1234567-8",
            "email": "valid@email.com",
            "nombre": "Test",
            "telefono": "0981",
            "documento": "1234567",
            "tipo_documento": "CI",
            "razon_social": "Test SA",
        },
        "compras_items": [
            {
                "id_producto": "ITEM-1",
                "nombre": "Test Item",
                "cantidad": 1,
                "precio_total": 100.0,
            }
        ],
    }

    res = test_client.post("/api/v1/pagopar/orders", json=invalid_payload)
    assert res.status_code == 422


def test_schema_rejects_invalid_email_format(test_client):
    invalid_payload = {
        "order_id": "ORD-INVALID-EMAIL",
        "monto_total": 50000.0,
        "descripcion_resumen": "Email validation test",
        "comprador": {
            "ruc": "1234567-8",
            "email": "not-an-email",
            "nombre": "Test",
            "telefono": "0981",
            "documento": "1234567",
            "tipo_documento": "CI",
            "razon_social": "Test SA",
        },
        "compras_items": [
            {
                "id_producto": "ITEM-1",
                "nombre": "Test Item",
                "cantidad": 1,
                "precio_total": 50000.0,
            }
        ],
    }

    res = test_client.post("/api/v1/pagopar/orders", json=invalid_payload)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_database_rollback_on_persistence_failure(monkeypatch, db_session, test_settings):
    async def mock_initiate(self, *args, **kwargs):
        return {
            "pagopar_hash": "rollback_hash_123",
            "checkout_url": "https://sandbox.pagopar.com/pagos/rollback_hash_123",
            "raw_response": {"respuesta": True},
        }

    monkeypatch.setattr(PagoparClient, "initiate_transaction", mock_initiate)

    service = PagoparPaymentService(custom_settings=test_settings)
    req = CreateOrderRequest(
        order_id="ORD-ROLLBACK-TEST",
        monto_total=10000.0,
        descripcion_resumen="Rollback test",
        comprador=BuyerModel(
            ruc="1234567-8",
            email="test@email.com",
            nombre="Rollback User",
            telefono="0981",
            documento="1234567",
            tipo_documento=DocumentType.CI,
            razon_social="User SA",
        ),
        compras_items=[
            OrderItemModel(
                id_producto="ITEM-1",
                nombre="Rollback Item",
                cantidad=1,
                precio_total=10000.0,
            )
        ],
    )

    # Force database commit to fail
    def failing_commit():
        raise RuntimeError("Simulated Disk IO Failure during commit")

    monkeypatch.setattr(db_session, "commit", failing_commit)

    with pytest.raises(PagoparError):
        await service.create_payment_order(db=db_session, request=req)

    # Ensure no dirty transaction survived
    tx = db_session.query(PagoparTransaction).filter(PagoparTransaction.order_id == "ORD-ROLLBACK-TEST").first()
    assert tx is None
