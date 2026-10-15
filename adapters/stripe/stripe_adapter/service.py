"""
Business logic and persistence orchestration for Stripe Adapter.
Guarantees ACID transactions, strict idempotency, and defense against duplicate processing.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from stripe_adapter.client import (
    StripeClient,
    StripeError,
    StripeGatewayError,
    StripeOrderNotFoundError,
    StripeSignatureError,
)
from stripe_adapter.config import Settings, settings
from stripe_adapter.db_models import StripeTransaction, StripeWebhookLog
from stripe_adapter.models import (
    CreateCheckoutSessionRequest,
    CreatePaymentIntentRequest,
    CurrencyHelper,
    OrderStatus,
    PaymentResponse,
    SyncPaymentResponse,
    WebhookProcessResult,
)

logger = logging.getLogger("stripe_adapter.service")


class StripePaymentService:
    """Core domain service for Stripe payment operations."""

    def __init__(
        self,
        client: Optional[StripeClient] = None,
        custom_settings: Optional[Settings] = None,
    ):
        self.cfg = custom_settings or settings
        self.client = client or StripeClient(self.cfg)

    def _transaction_to_response(self, tx: StripeTransaction) -> PaymentResponse:
        return PaymentResponse(
            order_id=tx.order_id,
            stripe_id=tx.stripe_id,
            payment_type=tx.payment_type,
            checkout_url=tx.checkout_url,
            client_secret=tx.client_secret,
            status=OrderStatus(tx.status),
            amount=tx.amount,
            amount_cents=tx.amount_cents,
            currency=tx.currency,
            customer_email=tx.customer_email,
            created_at=tx.created_at,
            updated_at=tx.updated_at,
            paid_at=tx.paid_at,
            payment_method=tx.payment_method,
            receipt_url=tx.receipt_url,
            details=tx.failure_reason if tx.status == OrderStatus.FAILED.value else tx.description,
        )

    async def create_checkout_session(
        self,
        db: Session,
        request: CreateCheckoutSessionRequest,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> PaymentResponse:
        """
        Creates a Stripe Checkout Session and persists the transaction idempotently.
        """
        # 1. Idempotency check via X-Idempotency-Key
        if idempotency_key:
            existing_by_key = (
                db.query(StripeTransaction)
                .filter(StripeTransaction.idempotency_key == idempotency_key)
                .first()
            )
            if existing_by_key:
                logger.info(
                    "Idempotent hit for idempotency_key=%s returning order_id=%s",
                    idempotency_key,
                    existing_by_key.order_id,
                )
                return self._transaction_to_response(existing_by_key)

        # 2. Check if order_id was already initiated
        existing_by_id = (
            db.query(StripeTransaction)
            .filter(StripeTransaction.order_id == request.order_id)
            .first()
        )
        if existing_by_id:
            logger.info("Order %s already exists, returning existing transaction", request.order_id)
            return self._transaction_to_response(existing_by_id)

        # 3. Call Stripe API
        gateway_result = await self.client.create_checkout_session(
            request=request,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

        session_id = gateway_result["session_id"]
        checkout_url = gateway_result["checkout_url"]
        raw_resp = gateway_result["raw_response"]
        amount_cents = CurrencyHelper.amount_to_cents(request.amount_total, request.currency)

        # 4. Atomic database persistence
        tx = StripeTransaction(
            order_id=request.order_id,
            idempotency_key=idempotency_key,
            stripe_id=session_id,
            payment_type="checkout_session",
            status=OrderStatus.PENDING_PAYMENT.value,
            amount=request.amount_total,
            amount_cents=amount_cents,
            currency=request.currency,
            customer_email=request.customer_email,
            description=request.description,
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
            raise StripeError(f"Database error persisting transaction: {exc}") from exc

        return self._transaction_to_response(tx)

    async def create_payment_intent(
        self,
        db: Session,
        request: CreatePaymentIntentRequest,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> PaymentResponse:
        """
        Creates a direct Stripe PaymentIntent and persists the transaction idempotently.
        """
        # 1. Idempotency check
        if idempotency_key:
            existing_by_key = (
                db.query(StripeTransaction)
                .filter(StripeTransaction.idempotency_key == idempotency_key)
                .first()
            )
            if existing_by_key:
                logger.info(
                    "Idempotent hit for idempotency_key=%s returning order_id=%s",
                    idempotency_key,
                    existing_by_key.order_id,
                )
                return self._transaction_to_response(existing_by_key)

        existing_by_id = (
            db.query(StripeTransaction)
            .filter(StripeTransaction.order_id == request.order_id)
            .first()
        )
        if existing_by_id:
            logger.info("Order %s already exists, returning existing transaction", request.order_id)
            return self._transaction_to_response(existing_by_id)

        # 2. Call Stripe API
        gateway_result = await self.client.create_payment_intent(
            request=request,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

        pi_id = gateway_result["payment_intent_id"]
        client_secret = gateway_result["client_secret"]
        raw_resp = gateway_result["raw_response"]
        amount_cents = CurrencyHelper.amount_to_cents(request.amount, request.currency)

        status_val = OrderStatus.PENDING_PAYMENT.value
        if gateway_result.get("status") == "succeeded":
            status_val = OrderStatus.PAID.value

        tx = StripeTransaction(
            order_id=request.order_id,
            idempotency_key=idempotency_key,
            stripe_id=pi_id,
            payment_intent_id=pi_id,
            payment_type="payment_intent",
            status=status_val,
            amount=request.amount,
            amount_cents=amount_cents,
            currency=request.currency,
            customer_email=request.customer_email,
            description=request.description,
            client_secret=client_secret,
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
            raise StripeError(f"Database error persisting transaction: {exc}") from exc

        return self._transaction_to_response(tx)

    def process_webhook(
        self,
        db: Session,
        raw_body: bytes,
        signature_header: Optional[str],
    ) -> WebhookProcessResult:
        """
        Validates cryptographically and idempotently processes Stripe payment webhook events.
        Guarantees defense against replay attacks and duplicate processing.
        """
        # Step A: Cryptographic signature verification
        is_valid, expected_sig, event_data = self.client.verify_webhook_signature(
            payload=raw_body,
            signature_header=signature_header,
            secret=self.cfg.stripe_webhook_secret,
            tolerance=self.cfg.webhook_tolerance_seconds,
        )

        event_id = event_data.get("id") or "unknown_event_id"
        event_type = event_data.get("type") or "unknown_type"

        if not is_valid:
            try:
                unverified_data = json.loads(raw_body.decode("utf-8", errors="replace"))
                if isinstance(unverified_data, dict):
                    event_id = unverified_data.get("id") or event_id
                    event_type = unverified_data.get("type") or event_type
            except Exception:
                pass

            logger.error("Security Alert: Invalid Stripe webhook signature header=%s", signature_header)
            audit_log = StripeWebhookLog(
                event_id=event_id,
                event_type=event_type,
                stripe_object_id=None,
                received_signature=signature_header or "none",
                calculated_signature=expected_sig,
                is_valid_signature=False,
                processed_status="SIGNATURE_FAILED",
                raw_payload=raw_body.decode("utf-8", errors="replace"),
                created_at=datetime.now(timezone.utc),
            )
            db.add(audit_log)
            db.commit()
            raise StripeSignatureError("Forbidden: Webhook signature verification failed")

        # Step B: Idempotency check against duplicate webhook events
        duplicate_check = db.query(StripeWebhookLog).filter(
            StripeWebhookLog.event_id == event_id,
            StripeWebhookLog.is_valid_signature == True,
            StripeWebhookLog.processed_status == "PROCESSED",
        ).first()

        if duplicate_check is not None:
            logger.info("Idempotent webhook: event_id=%s already processed", event_id)
            duplicate_log = StripeWebhookLog(
                event_id=event_id,
                event_type=event_type,
                stripe_object_id=duplicate_check.stripe_object_id,
                received_signature=signature_header or "",
                calculated_signature=expected_sig,
                is_valid_signature=True,
                processed_status="DUPLICATE_IGNORED",
                raw_payload=raw_body.decode("utf-8", errors="replace"),
                created_at=datetime.now(timezone.utc),
            )
            db.add(duplicate_log)
            db.commit()
            return WebhookProcessResult(
                status="already_processed",
                event_id=event_id,
                event_type=event_type,
                order_id=None,
                payment_id=duplicate_check.stripe_object_id,
                processed=False,
                details="Duplicate webhook event ignored",
            )

        # Step C: Process event by type
        data_object: Dict[str, Any] = event_data.get("data", {}).get("object", {})
        stripe_obj_id = data_object.get("id")
        processed_status = "PROCESSED"
        matched_tx: Optional[StripeTransaction] = None

        if event_type == "checkout.session.completed":
            session_id = data_object.get("id")
            order_id = data_object.get("client_reference_id") or data_object.get("metadata", {}).get("order_id")

            query = db.query(StripeTransaction)
            if session_id:
                matched_tx = query.filter(StripeTransaction.stripe_id == session_id).first()
            if not matched_tx and order_id:
                matched_tx = db.query(StripeTransaction).filter(StripeTransaction.order_id == order_id).first()

            if matched_tx:
                payment_status = data_object.get("payment_status")
                if payment_status == "paid":
                    matched_tx.status = OrderStatus.PAID.value
                    matched_tx.paid_at = datetime.now(timezone.utc)
                else:
                    matched_tx.status = OrderStatus.PENDING_PAYMENT.value
                matched_tx.payment_intent_id = data_object.get("payment_intent") or matched_tx.payment_intent_id
                matched_tx.updated_at = datetime.now(timezone.utc)
                matched_tx.raw_last_response = json.dumps(data_object)
            else:
                logger.warning("Checkout session completed for unknown order/session: %s", session_id)
                processed_status = "ORDER_NOT_FOUND"

        elif event_type == "payment_intent.succeeded":
            pi_id = data_object.get("id")
            order_id = data_object.get("metadata", {}).get("order_id")

            query = db.query(StripeTransaction)
            if pi_id:
                matched_tx = query.filter(
                    (StripeTransaction.stripe_id == pi_id) | (StripeTransaction.payment_intent_id == pi_id)
                ).first()
            if not matched_tx and order_id:
                matched_tx = db.query(StripeTransaction).filter(StripeTransaction.order_id == order_id).first()

            if matched_tx:
                matched_tx.status = OrderStatus.PAID.value
                matched_tx.paid_at = datetime.now(timezone.utc)
                matched_tx.payment_intent_id = pi_id
                # Extract payment method details and receipt if available
                charges = data_object.get("charges", {}).get("data", [])
                if charges and isinstance(charges, list) and len(charges) > 0:
                    matched_tx.receipt_url = charges[0].get("receipt_url")
                    matched_tx.payment_method = charges[0].get("payment_method_details", {}).get("type") or "card"
                matched_tx.updated_at = datetime.now(timezone.utc)
                matched_tx.raw_last_response = json.dumps(data_object)
            else:
                logger.warning("PaymentIntent succeeded for unknown payment: %s", pi_id)
                processed_status = "ORDER_NOT_FOUND"

        elif event_type == "payment_intent.payment_failed":
            pi_id = data_object.get("id")
            order_id = data_object.get("metadata", {}).get("order_id")

            query = db.query(StripeTransaction)
            if pi_id:
                matched_tx = query.filter(
                    (StripeTransaction.stripe_id == pi_id) | (StripeTransaction.payment_intent_id == pi_id)
                ).first()
            if not matched_tx and order_id:
                matched_tx = db.query(StripeTransaction).filter(StripeTransaction.order_id == order_id).first()

            if matched_tx:
                matched_tx.status = OrderStatus.FAILED.value
                last_err = data_object.get("last_payment_error", {})
                matched_tx.failure_reason = last_err.get("message") or "Payment rejected by Stripe"
                matched_tx.updated_at = datetime.now(timezone.utc)
                matched_tx.raw_last_response = json.dumps(data_object)
            else:
                logger.warning("PaymentIntent failed for unknown payment: %s", pi_id)
                processed_status = "ORDER_NOT_FOUND"

        else:
            logger.info("Received unhandled Stripe webhook event type: %s", event_type)
            processed_status = "UNHANDLED_EVENT"

        # Step D: Log verified webhook
        audit_log = StripeWebhookLog(
            event_id=event_id,
            event_type=event_type,
            stripe_object_id=stripe_obj_id,
            received_signature=signature_header or "",
            calculated_signature=expected_sig,
            is_valid_signature=True,
            processed_status=processed_status,
            raw_payload=raw_body.decode("utf-8", errors="replace"),
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit_log)
        db.commit()

        return WebhookProcessResult(
            status="success",
            event_id=event_id,
            event_type=event_type,
            order_id=matched_tx.order_id if matched_tx else None,
            payment_id=matched_tx.stripe_id if matched_tx else stripe_obj_id,
            processed=processed_status == "PROCESSED",
            details=f"Processed event {event_type} with status {processed_status}",
        )

    async def sync_payment_status(
        self,
        db: Session,
        payment_id: str,
        correlation_id: Optional[str] = None,
    ) -> SyncPaymentResponse:
        """
        Actively queries Stripe polling endpoint to refresh payment state.
        Serves as resilience mechanism when webhooks are lost or delayed.
        """
        tx = (
            db.query(StripeTransaction)
            .filter(
                (StripeTransaction.order_id == payment_id)
                | (StripeTransaction.stripe_id == payment_id)
                | (StripeTransaction.payment_intent_id == payment_id)
            )
            .first()
        )
        if not tx:
            raise StripeOrderNotFoundError(f"Payment '{payment_id}' not found in local database")

        previous_status = OrderStatus(tx.status)
        current_status = previous_status
        gateway_data: Dict[str, Any] = {}

        if tx.payment_type == "checkout_session":
            gateway_data = await self.client.get_checkout_session(tx.stripe_id, correlation_id=correlation_id)
            payment_status = gateway_data.get("payment_status")
            if payment_status == "paid" and previous_status != OrderStatus.PAID:
                tx.status = OrderStatus.PAID.value
                tx.paid_at = datetime.now(timezone.utc)
                tx.payment_intent_id = gateway_data.get("payment_intent") or tx.payment_intent_id
                tx.updated_at = datetime.now(timezone.utc)
                tx.raw_last_response = json.dumps(gateway_data)
                db.commit()
                db.refresh(tx)
                current_status = OrderStatus.PAID
                logger.info("Order %s updated to PAID via CheckoutSession sync", tx.order_id)

        elif tx.payment_type == "payment_intent":
            gateway_data = await self.client.get_payment_intent(tx.stripe_id, correlation_id=correlation_id)
            pi_status = gateway_data.get("status")
            if pi_status == "succeeded" and previous_status != OrderStatus.PAID:
                tx.status = OrderStatus.PAID.value
                tx.paid_at = datetime.now(timezone.utc)
                charges = gateway_data.get("charges", {}).get("data", [])
                if charges and isinstance(charges, list) and len(charges) > 0:
                    tx.receipt_url = charges[0].get("receipt_url")
                    tx.payment_method = charges[0].get("payment_method_details", {}).get("type") or "card"
                tx.updated_at = datetime.now(timezone.utc)
                tx.raw_last_response = json.dumps(gateway_data)
                db.commit()
                db.refresh(tx)
                current_status = OrderStatus.PAID
                logger.info("Order %s updated to PAID via PaymentIntent sync", tx.order_id)
            elif pi_status == "canceled" and previous_status != OrderStatus.CANCELLED:
                tx.status = OrderStatus.CANCELLED.value
                tx.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(tx)
                current_status = OrderStatus.CANCELLED

        return SyncPaymentResponse(
            order_id=tx.order_id,
            stripe_id=tx.stripe_id,
            previous_status=previous_status,
            current_status=current_status,
            synced=True,
            gateway_response=gateway_data,
            details=f"Synced successfully with Stripe for {tx.stripe_id}",
        )

    def get_payment_by_id(self, db: Session, payment_id: str) -> PaymentResponse:
        """Retrieves payment record by order_id or Stripe identifier."""
        tx = (
            db.query(StripeTransaction)
            .filter(
                (StripeTransaction.order_id == payment_id)
                | (StripeTransaction.stripe_id == payment_id)
                | (StripeTransaction.payment_intent_id == payment_id)
            )
            .first()
        )
        if not tx:
            raise StripeOrderNotFoundError(f"Payment '{payment_id}' was not found")
        return self._transaction_to_response(tx)
