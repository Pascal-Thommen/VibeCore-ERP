"""
Business logic and persistence orchestration for Pagopar Adapter.
Guarantees ACID transactions, strict idempotency, and defense against duplicate processing.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from pagopar.client import (
    PagoparClient,
    PagoparError,
    PagoparGatewayError,
    PagoparOrderNotFoundError,
    PagoparSignatureError,
)
from pagopar.config import Settings, settings
from pagopar.db_models import PagoparTransaction, PagoparWebhookLog
from pagopar.models import (
    CreateOrderRequest,
    OrderResponse,
    OrderStatus,
    PagoparWebhookPayload,
    SyncOrderResponse,
    WebhookProcessResult,
)

logger = logging.getLogger("pagopar.service")


class PagoparPaymentService:
    """Core domain service for Pagopar payment operations."""

    def __init__(
        self,
        client: Optional[PagoparClient] = None,
        custom_settings: Optional[Settings] = None,
    ):
        self.cfg = custom_settings or settings
        self.client = client or PagoparClient(self.cfg)

    def _transaction_to_response(self, tx: PagoparTransaction) -> OrderResponse:
        return OrderResponse(
            order_id=tx.order_id,
            pagopar_hash=tx.pagopar_hash,
            checkout_url=tx.checkout_url,
            status=OrderStatus(tx.status),
            monto_total=tx.monto_total,
            currency=tx.currency,
            created_at=tx.created_at,
            updated_at=tx.updated_at,
            paid_at=tx.paid_at,
            payment_method=tx.payment_method,
            receipt_number=tx.receipt_number,
            details=f"Buyer: {tx.buyer_name} ({tx.buyer_ruc})",
        )

    async def create_payment_order(
        self,
        db: Session,
        request: CreateOrderRequest,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> OrderResponse:
        """
        Creates an order with Pagopar API v2 and records it in the local transactional store.
        If idempotency key or order ID is repeated, returns the existing record without duplicate charges.
        """
        # 1. Check idempotency key if provided
        if idempotency_key:
            existing_by_key = (
                db.query(PagoparTransaction)
                .filter(PagoparTransaction.idempotency_key == idempotency_key)
                .first()
            )
            if existing_by_key:
                logger.info(
                    "Idempotent hit for idempotency_key=%s returning order_id=%s",
                    idempotency_key,
                    existing_by_key.order_id,
                )
                return self._transaction_to_response(existing_by_key)

        # 2. Check if order_id was already created
        existing_by_id = (
            db.query(PagoparTransaction)
            .filter(PagoparTransaction.order_id == request.order_id)
            .first()
        )
        if existing_by_id:
            logger.info("Order %s already exists, returning existing transaction", request.order_id)
            return self._transaction_to_response(existing_by_id)

        # 3. Request transaction creation from Pagopar Gateway
        gateway_result = await self.client.initiate_transaction(
            order_id=request.order_id,
            monto_total=request.monto_total,
            description=request.descripcion_resumen,
            buyer=request.comprador,
            items=request.compras_items,
            fecha_maxima_pago=request.fecha_maxima_pago,
            correlation_id=correlation_id,
        )

        pagopar_hash = gateway_result["pagopar_hash"]
        checkout_url = gateway_result["checkout_url"]
        raw_resp = gateway_result["raw_response"]

        # 4. Atomic database persistence
        tx = PagoparTransaction(
            order_id=request.order_id,
            idempotency_key=idempotency_key,
            pagopar_hash=pagopar_hash,
            status=OrderStatus.PENDING_PAYMENT.value,
            monto_total=request.monto_total,
            currency="PYG",
            buyer_email=request.comprador.email,
            buyer_ruc=request.comprador.ruc,
            buyer_name=request.comprador.nombre,
            description=request.descripcion_resumen,
            checkout_url=checkout_url,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            raw_order_payload=request.model_dump_json(),
            raw_last_response=json.dumps(raw_resp),
        )

        try:
            db.add(tx)
            db.commit()
            db.refresh(tx)
        except Exception as exc:
            db.rollback()
            logger.error("Failed to persist transaction for order %s: %s", request.order_id, exc)
            raise PagoparError(f"Database error persisting transaction: {exc}") from exc

        return self._transaction_to_response(tx)

    def process_webhook(
        self,
        db: Session,
        payload: PagoparWebhookPayload,
        raw_payload_str: Optional[str] = None,
    ) -> WebhookProcessResult:
        """
        Validates cryptographically and idempotently processes Pagopar payment notifications.
        Prevents duplicate accounting entries and marks orders as PAID.
        """
        processed_items = []

        for item in payload.resultado:
            # Step A: Cryptographic signature verification
            is_valid = self.client.verify_webhook_signature(
                self.cfg.pagopar_private_key,
                item.hash_pedido,
                item.token,
            )

            expected_token = self.client.compute_webhook_token(
                self.cfg.pagopar_private_key,
                item.hash_pedido,
            )

            if not is_valid:
                logger.error(
                    "Security Alert: Invalid webhook signature for hash_pedido=%s received_token=%s",
                    item.hash_pedido,
                    item.token,
                )
                # Audit the malicious or malformed attempt
                log_entry = PagoparWebhookLog(
                    hash_pedido=item.hash_pedido,
                    identificador_pago=item.identificador_pago,
                    received_token=item.token,
                    calculated_token=expected_token,
                    is_valid_signature=False,
                    is_paid=item.pagado,
                    amount=float(item.monto),
                    processed_status="SIGNATURE_FAILED",
                    raw_payload=raw_payload_str or json.dumps(item.model_dump()),
                    created_at=datetime.now(timezone.utc),
                )
                db.add(log_entry)
                db.commit()
                raise PagoparSignatureError(
                    f"Signature validation failed for transaction hash {item.hash_pedido}"
                )

            # Step B: Idempotency check against duplicate webhook events
            duplicate_check = db.query(PagoparWebhookLog).filter(
                PagoparWebhookLog.hash_pedido == item.hash_pedido,
                PagoparWebhookLog.is_valid_signature == True,
                PagoparWebhookLog.processed_status == "PROCESSED",
            )
            if item.identificador_pago is not None:
                duplicate_check = duplicate_check.filter(
                    PagoparWebhookLog.identificador_pago == item.identificador_pago
                )

            if duplicate_check.first() is not None:
                logger.info(
                    "Idempotent webhook: hash_pedido=%s payment_id=%s already processed",
                    item.hash_pedido,
                    item.identificador_pago,
                )
                duplicate_log = PagoparWebhookLog(
                    hash_pedido=item.hash_pedido,
                    identificador_pago=item.identificador_pago,
                    received_token=item.token,
                    calculated_token=expected_token,
                    is_valid_signature=True,
                    is_paid=item.pagado,
                    amount=float(item.monto),
                    processed_status="DUPLICATE_IGNORED",
                    raw_payload=raw_payload_str or json.dumps(item.model_dump()),
                    created_at=datetime.now(timezone.utc),
                )
                db.add(duplicate_log)
                db.commit()
                processed_items.append({
                    "hash_pedido": item.hash_pedido,
                    "status": "already_processed",
                    "pagado": item.pagado,
                })
                continue

            # Step C: Update transaction status
            tx = (
                db.query(PagoparTransaction)
                .filter(PagoparTransaction.pagopar_hash == item.hash_pedido)
                .first()
            )

            processed_status = "PROCESSED"
            if tx:
                if item.pagado:
                    tx.status = OrderStatus.PAID.value
                    tx.paid_at = datetime.now(timezone.utc)
                    tx.payment_method = item.forma_pago or "Pagopar"
                    tx.receipt_number = item.numero_comprobante
                else:
                    tx.status = OrderStatus.FAILED.value
                tx.updated_at = datetime.now(timezone.utc)
                tx.raw_last_response = json.dumps(item.model_dump())
            else:
                logger.warning("Webhook received for unknown transaction hash: %s", item.hash_pedido)
                processed_status = "ORDER_NOT_FOUND"

            # Step D: Log verified webhook event
            audit_log = PagoparWebhookLog(
                hash_pedido=item.hash_pedido,
                identificador_pago=item.identificador_pago,
                received_token=item.token,
                calculated_token=expected_token,
                is_valid_signature=True,
                is_paid=item.pagado,
                amount=float(item.monto),
                processed_status=processed_status,
                raw_payload=raw_payload_str or json.dumps(item.model_dump()),
                created_at=datetime.now(timezone.utc),
            )
            db.add(audit_log)
            db.commit()

            processed_items.append({
                "hash_pedido": item.hash_pedido,
                "order_id": tx.order_id if tx else None,
                "status": processed_status,
                "pagado": item.pagado,
            })

        return WebhookProcessResult(
            status="success",
            processed_count=len(processed_items),
            items=processed_items,
        )

    async def sync_order_status(
        self,
        db: Session,
        order_id: str,
        correlation_id: Optional[str] = None,
    ) -> SyncOrderResponse:
        """
        Actively queries Pagopar polling endpoint to refresh order state.
        Serves as resilience mechanism when webhooks are lost or delayed.
        """
        tx = db.query(PagoparTransaction).filter(PagoparTransaction.order_id == order_id).first()
        if not tx:
            raise PagoparOrderNotFoundError(f"Order '{order_id}' not found in local database")

        if not tx.pagopar_hash:
            raise PagoparGatewayError(f"Order '{order_id}' lacks a Pagopar transaction hash")

        previous_status = OrderStatus(tx.status)
        poll_res = await self.client.poll_order_status(tx.pagopar_hash, correlation_id=correlation_id)

        is_paid = poll_res.get("pagado", False)
        current_status = previous_status

        if is_paid and previous_status != OrderStatus.PAID:
            tx.status = OrderStatus.PAID.value
            tx.paid_at = datetime.now(timezone.utc)
            tx.payment_method = poll_res.get("forma_pago") or tx.payment_method or "Pagopar"
            tx.updated_at = datetime.now(timezone.utc)
            tx.raw_last_response = json.dumps(poll_res.get("raw_response", {}))
            db.commit()
            db.refresh(tx)
            current_status = OrderStatus.PAID
            logger.info("Order %s updated to PAID via polling synchronization", order_id)

        return SyncOrderResponse(
            order_id=tx.order_id,
            pagopar_hash=tx.pagopar_hash,
            previous_status=previous_status,
            current_status=current_status,
            synced=True,
            gateway_response=poll_res,
            details=f"Polled Pagopar successfully for hash {tx.pagopar_hash}",
        )

    def get_order_by_id(self, db: Session, order_id: str) -> OrderResponse:
        """Retrieves order status and metadata by business order_id."""
        tx = db.query(PagoparTransaction).filter(PagoparTransaction.order_id == order_id).first()
        if not tx:
            raise PagoparOrderNotFoundError(f"Order '{order_id}' was not found")
        return self._transaction_to_response(tx)
