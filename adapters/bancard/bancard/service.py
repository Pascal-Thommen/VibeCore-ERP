"""Business logic service for Bancard vPOS 2.0 and Paraguay Catastro QR payments."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from bancard.client import BancardGatewayClient, BancardGatewayError
from bancard.config import settings
from bancard.constants import (
    CURRENCY_CODE_PYG,
    CURRENCY_PYG,
    RESPONSE_CODE_APPROVED,
    PaymentMethod,
    TransactionStatus,
)
from bancard.crypto import (
    format_bancard_amount,
    generate_single_buy_token,
    verify_bancard_confirmation_token,
)
from bancard.database import BancardTransaction, TransactionAuditLog
from bancard.metrics import metrics
from bancard.models import (
    BancardWebhookPayload,
    BancardWebhookResponse,
    CardCatastroRequest,
    CardCatastroResponse,
    CatastroQrGenerateRequest,
    CatastroQrGenerateResponse,
    CatastroQrStatusResponse,
    RollbackResponse,
    SingleBuyInitRequest,
    SingleBuyInitResponse,
    TokenChargeRequest,
    TokenChargeResponse,
)
from bancard.qr import (
    build_bancard_catastro_qr_payload,
    generate_qr_image_data_uri,
)
from bancard.webhook_dispatcher import dispatcher

logger = logging.getLogger("bancard.service")


class BancardPaymentService:
    def __init__(self, client: Optional[BancardGatewayClient] = None) -> None:
        self.client = client or BancardGatewayClient()

    def _next_shop_process_id(self, db: Session) -> int:
        """Atomically generate the next sequential shop_process_id."""
        max_id = db.query(func.max(BancardTransaction.shop_process_id)).scalar()
        if max_id is None or max_id < 100000:
            return 100001
        return int(max_id) + 1

    def initialize_single_buy(self, db: Session, req: SingleBuyInitRequest) -> SingleBuyInitResponse:
        start_time = time.time()

        # Idempotency check
        if req.idempotency_key:
            existing = (
                db.query(BancardTransaction)
                .filter(BancardTransaction.idempotency_key == req.idempotency_key)
                .first()
            )
            if existing:
                logger.info(
                    "Idempotent single_buy request resolved to existing transaction",
                    extra={"idempotency_key": req.idempotency_key, "shop_process_id": existing.shop_process_id},
                )
                checkout_url = f"{self.client.base_url}/payment/single_buy?process_id={existing.bancard_process_id}"
                script_url = f"{self.client.base_url}/checkout.js"
                return SingleBuyInitResponse(
                    shop_process_id=existing.shop_process_id,
                    process_id=existing.bancard_process_id or "",
                    token=existing.bancard_token or "",
                    status=existing.status,
                    amount=existing.amount,
                    currency=existing.currency,
                    checkout_url=checkout_url,
                    script_url=script_url,
                )

        shop_process_id = self._next_shop_process_id(db)
        amount_dec = Decimal(str(req.amount))
        token = generate_single_buy_token(
            settings.bancard_private_key,
            shop_process_id,
            amount_dec,
            req.currency,
        )

        # Call gateway (strict Zero Mock: require genuine process_id from Bancard)
        gw_resp = self.client.single_buy(
            shop_process_id=shop_process_id,
            amount=amount_dec,
            currency=req.currency,
            description=req.description,
            return_url=req.return_url,
            cancel_url=req.cancel_url,
        )
        process_id = gw_resp.get("process_id")
        if not process_id:
            raise BancardGatewayError(
                f"Bancard gateway did not return a valid process_id: {gw_resp}",
                response_data=gw_resp,
                status_code=502,
            )

        tx_id = str(uuid.uuid4())
        tx = BancardTransaction(
            id=tx_id,
            idempotency_key=req.idempotency_key,
            shop_process_id=shop_process_id,
            user_id=req.user_id,
            amount=amount_dec,
            currency=req.currency,
            payment_method=PaymentMethod.SINGLE_BUY.value,
            status=TransactionStatus.PENDING.value,
            description=req.description,
            bancard_token=token,
            bancard_process_id=process_id,
            raw_request=req.model_dump(mode="json"),
        )
        db.add(tx)
        db.flush()

        audit = TransactionAuditLog(
            id=str(uuid.uuid4()),
            transaction_id=tx_id,
            shop_process_id=shop_process_id,
            previous_status=None,
            new_status=TransactionStatus.PENDING.value,
            reason="Initialized single_buy session",
            actor=req.user_id or "system",
            details={"description": req.description, "amount": str(amount_dec)},
        )
        db.add(audit)
        db.commit()
        db.refresh(tx)

        duration = time.time() - start_time
        metrics.record_transaction(TransactionStatus.PENDING.value, PaymentMethod.SINGLE_BUY.value, duration)

        checkout_url = f"{self.client.base_url}/payment/single_buy?process_id={process_id}"
        script_url = f"{self.client.base_url}/checkout.js"

        return SingleBuyInitResponse(
            shop_process_id=shop_process_id,
            process_id=process_id,
            token=token,
            status=tx.status,
            amount=tx.amount,
            currency=tx.currency,
            checkout_url=checkout_url,
            script_url=script_url,
        )

    def initialize_card_catastro(self, db: Session, req: CardCatastroRequest) -> CardCatastroResponse:
        """Initialize card catastro (tokenization) session with Bancard."""
        gw_resp = self.client.cards_new(
            card_id=req.card_id,
            user_id=req.user_id,
            user_cell_phone=req.user_cell_phone,
            user_mail=req.user_mail,
            return_url=req.return_url,
        )
        process_id = gw_resp.get("process_id")
        if not process_id:
            raise BancardGatewayError(
                f"Bancard cards_new did not return a valid process_id: {gw_resp}",
                response_data=gw_resp,
                status_code=502,
            )

        return CardCatastroResponse(
            process_id=process_id,
            status="pending",
            user_id=req.user_id,
            card_id=req.card_id,
        )

    def execute_token_charge(self, db: Session, req: TokenChargeRequest) -> TokenChargeResponse:
        start_time = time.time()

        # Idempotency check
        if req.idempotency_key:
            existing = (
                db.query(BancardTransaction)
                .filter(BancardTransaction.idempotency_key == req.idempotency_key)
                .first()
            )
            if existing:
                return TokenChargeResponse(
                    shop_process_id=existing.shop_process_id,
                    status=existing.status,
                    response_code=existing.response_code or "",
                    response_description=existing.response_description or "",
                    ticket_number=existing.ticket_number,
                    authorization_number=existing.authorization_number,
                )

        shop_process_id = self._next_shop_process_id(db)
        amount_dec = Decimal(str(req.amount))

        tx_id = str(uuid.uuid4())
        tx = BancardTransaction(
            id=tx_id,
            idempotency_key=req.idempotency_key,
            shop_process_id=shop_process_id,
            user_id=req.user_id,
            amount=amount_dec,
            currency=req.currency,
            payment_method=PaymentMethod.TOKEN_CHARGE.value,
            status=TransactionStatus.PENDING.value,
            description=req.description,
            alias_token=req.alias_token,
            raw_request=req.model_dump(mode="json"),
        )
        db.add(tx)
        db.flush()

        # Call gateway charge (strict Zero Mock: genuine confirmation required)
        try:
            gw_resp = self.client.charge(
                shop_process_id=shop_process_id,
                amount=amount_dec,
                currency=req.currency,
                alias_token=req.alias_token,
                description=req.description,
            )
            op = gw_resp.get("confirmation", {}).get("operation") or gw_resp.get("operation", {})
            resp_code = op.get("response_code")
            resp_desc = op.get("response_description", "Transaccion procesada")
            ticket = op.get("ticket_number")
            auth_no = op.get("authorization_number")
            is_approved = resp_code == RESPONSE_CODE_APPROVED
            final_status = TransactionStatus.APPROVED.value if is_approved else TransactionStatus.REJECTED.value
        except BancardGatewayError as exc:
            logger.error("Bancard gateway charge error: %s", str(exc))
            resp_code = "99"
            resp_desc = f"Gateway error: {str(exc)}"
            ticket = None
            auth_no = None
            is_approved = False
            final_status = TransactionStatus.REJECTED.value
        except Exception as exc:
            logger.error("Unexpected charge error: %s", str(exc))
            resp_code = "99"
            resp_desc = f"Execution error: {str(exc)}"
            ticket = None
            auth_no = None
            is_approved = False
            final_status = TransactionStatus.REJECTED.value

        tx.status = final_status
        tx.response_code = resp_code
        tx.response_description = resp_desc
        tx.ticket_number = ticket
        tx.authorization_number = auth_no
        tx.updated_at = datetime.now(timezone.utc)

        audit = TransactionAuditLog(
            id=str(uuid.uuid4()),
            transaction_id=tx_id,
            shop_process_id=shop_process_id,
            previous_status=TransactionStatus.PENDING.value,
            new_status=final_status,
            reason=f"Charge executed: {resp_desc}",
            actor=req.user_id,
            details={"response_code": resp_code, "ticket_number": ticket},
        )
        db.add(audit)
        db.commit()
        db.refresh(tx)

        duration = time.time() - start_time
        metrics.record_transaction(final_status, PaymentMethod.TOKEN_CHARGE.value, duration)

        # Dispatch signed webhook
        event_name = "payment.bancard.approved" if is_approved else "payment.bancard.rejected"
        dispatcher.dispatch_event(
            db=db,
            event_type=event_name,
            data={
                "shop_process_id": tx.shop_process_id,
                "user_id": tx.user_id,
                "amount": str(tx.amount),
                "currency": tx.currency,
                "payment_method": tx.payment_method,
                "status": tx.status,
                "response_code": tx.response_code,
                "ticket_number": tx.ticket_number,
                "authorization_number": tx.authorization_number,
                "idempotency_key": tx.idempotency_key,
            },
        )

        return TokenChargeResponse(
            shop_process_id=tx.shop_process_id,
            status=tx.status,
            response_code=tx.response_code or "",
            response_description=tx.response_description or "",
            ticket_number=tx.ticket_number,
            authorization_number=tx.authorization_number,
        )

    def execute_rollback(
        self,
        db: Session,
        shop_process_id: int,
        reason: Optional[str] = "Customer cancellation or timeout",
    ) -> RollbackResponse:
        start_time = time.time()

        tx = (
            db.query(BancardTransaction)
            .filter(BancardTransaction.shop_process_id == shop_process_id)
            .first()
        )
        if not tx:
            raise ValueError(f"Transaction with shop_process_id {shop_process_id} not found")

        # Idempotent return if already reversed
        if tx.status == TransactionStatus.REVERSED.value:
            return RollbackResponse(
                shop_process_id=tx.shop_process_id,
                status=tx.status,
                response_code="00",
                response_description="Transaction already reversed",
            )

        # Check eligibility: only PENDING or APPROVED can be rolled back
        if tx.status not in [TransactionStatus.PENDING.value, TransactionStatus.APPROVED.value]:
            raise ValueError(f"Cannot rollback transaction in terminal status: {tx.status}")

        # Real gateway rollback (strict Zero Mock: do not record reversal if Bancard fails or rejects)
        gw_resp = self.client.rollback(shop_process_id)
        if isinstance(gw_resp, dict) and gw_resp.get("status") == "error":
            msgs = gw_resp.get("messages", ["Rollback rejected by Bancard"])
            raise BancardGatewayError(
                f"Bancard rollback rejected: {msgs}",
                response_data=gw_resp,
                status_code=400,
            )

        prev_status = tx.status
        tx.status = TransactionStatus.REVERSED.value
        tx.response_code = "00"
        tx.response_description = f"Reversed: {reason}"
        tx.updated_at = datetime.now(timezone.utc)

        audit = TransactionAuditLog(
            id=str(uuid.uuid4()),
            transaction_id=tx.id,
            shop_process_id=shop_process_id,
            previous_status=prev_status,
            new_status=TransactionStatus.REVERSED.value,
            reason=reason,
            actor="system",
            details={"previous_status": prev_status},
        )
        db.add(audit)
        db.commit()
        db.refresh(tx)

        duration = time.time() - start_time
        metrics.record_transaction(TransactionStatus.REVERSED.value, tx.payment_method, duration)

        # Dispatch signed webhook
        dispatcher.dispatch_event(
            db=db,
            event_type="payment.bancard.reversed",
            data={
                "shop_process_id": tx.shop_process_id,
                "user_id": tx.user_id,
                "amount": str(tx.amount),
                "currency": tx.currency,
                "status": tx.status,
                "reason": reason,
            },
        )

        return RollbackResponse(
            shop_process_id=tx.shop_process_id,
            status=tx.status,
            response_code="00",
            response_description=tx.response_description,
        )

    def process_bancard_confirmation(self, db: Session, payload: BancardWebhookPayload) -> BancardWebhookResponse:
        op = payload.operation
        amount_dec = Decimal(str(op.amount))

        # Cryptographic verification
        is_valid = verify_bancard_confirmation_token(
            private_key=settings.bancard_private_key,
            shop_process_id=op.shop_process_id,
            amount=amount_dec,
            currency=op.currency,
            received_token=op.token,
            response_code=op.response_code,
        )
        if not is_valid:
            logger.error("Bancard confirmation hash verification failed", extra={"shop_process_id": op.shop_process_id})
            raise ValueError("Bancard security token mismatch; confirmation rejected.")

        tx = (
            db.query(BancardTransaction)
            .filter(BancardTransaction.shop_process_id == op.shop_process_id)
            .first()
        )

        is_approved = op.response_code == RESPONSE_CODE_APPROVED
        new_status = TransactionStatus.APPROVED.value if is_approved else TransactionStatus.REJECTED.value

        if not tx:
            # Standalone webhook received for externally created order
            tx_id = str(uuid.uuid4())
            tx = BancardTransaction(
                id=tx_id,
                shop_process_id=op.shop_process_id,
                amount=amount_dec,
                currency=op.currency,
                payment_method=PaymentMethod.SINGLE_BUY.value,
                status=new_status,
                response_code=op.response_code,
                response_description=op.response_description or "",
                ticket_number=op.ticket_number,
                authorization_number=op.authorization_number,
                raw_response=payload.model_dump(mode="json"),
            )
            db.add(tx)
            db.flush()
            prev_status = None
        else:
            # Idempotent handling: if already in target status, return 200 without duplicate event
            if tx.status in [TransactionStatus.APPROVED.value, TransactionStatus.REVERSED.value]:
                return BancardWebhookResponse(
                    status="success",
                    shop_process_id=tx.shop_process_id,
                    transaction_status=tx.status,
                    message="Confirmation already recorded (idempotent)",
                )

            prev_status = tx.status
            tx.status = new_status
            tx.response_code = op.response_code
            tx.response_description = op.response_description or tx.response_description
            tx.ticket_number = op.ticket_number or tx.ticket_number
            tx.authorization_number = op.authorization_number or tx.authorization_number
            tx.raw_response = payload.model_dump(mode="json")
            tx.updated_at = datetime.now(timezone.utc)

        audit = TransactionAuditLog(
            id=str(uuid.uuid4()),
            transaction_id=tx.id,
            shop_process_id=tx.shop_process_id,
            previous_status=prev_status,
            new_status=new_status,
            reason=f"Webhook confirmation received: response_code={op.response_code}",
            actor="bancard_webhook",
            details={"ticket_number": op.ticket_number, "response_description": op.response_description},
        )
        db.add(audit)
        db.commit()
        db.refresh(tx)

        metrics.record_transaction(new_status, tx.payment_method, 0.0)

        # Dispatch signed event to AIBill and VibeCore ERP
        event_name = "payment.bancard.approved" if is_approved else "payment.bancard.rejected"
        dispatcher.dispatch_event(
            db=db,
            event_type=event_name,
            data={
                "shop_process_id": tx.shop_process_id,
                "user_id": tx.user_id,
                "amount": str(tx.amount),
                "currency": tx.currency,
                "payment_method": tx.payment_method,
                "status": tx.status,
                "response_code": tx.response_code,
                "response_description": tx.response_description,
                "ticket_number": tx.ticket_number,
                "authorization_number": tx.authorization_number,
                "idempotency_key": tx.idempotency_key,
            },
        )

        return BancardWebhookResponse(
            status="success",
            shop_process_id=tx.shop_process_id,
            transaction_status=tx.status,
            message="Confirmation processed successfully",
        )

    def generate_catastro_qr(self, db: Session, req: CatastroQrGenerateRequest) -> CatastroQrGenerateResponse:
        start_time = time.time()

        # Idempotency check
        if req.idempotency_key:
            existing = (
                db.query(BancardTransaction)
                .filter(BancardTransaction.idempotency_key == req.idempotency_key)
                .first()
            )
            if existing and existing.qr_payload:
                qr_uri = generate_qr_image_data_uri(existing.qr_payload)
                return CatastroQrGenerateResponse(
                    shop_process_id=existing.shop_process_id,
                    qr_payload=existing.qr_payload,
                    qr_image_data_uri=qr_uri,
                    status=existing.status,
                    amount=existing.amount,
                    currency=existing.currency,
                    expires_at=existing.expires_at or datetime.now(timezone.utc),
                )

        shop_process_id = self._next_shop_process_id(db)
        amount_dec = Decimal(str(req.amount))
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=req.expires_in_minutes)

        qr_payload = build_bancard_catastro_qr_payload(
            shop_process_id=shop_process_id,
            amount=amount_dec,
            description=req.description,
        )
        qr_image_uri = generate_qr_image_data_uri(qr_payload)

        tx_id = str(uuid.uuid4())
        tx = BancardTransaction(
            id=tx_id,
            idempotency_key=req.idempotency_key,
            shop_process_id=shop_process_id,
            user_id=req.user_id,
            amount=amount_dec,
            currency=req.currency,
            payment_method=PaymentMethod.CATASTRO_QR.value,
            status=TransactionStatus.PENDING.value,
            description=req.description,
            qr_payload=qr_payload,
            expires_at=expires_at,
            raw_request=req.model_dump(mode="json"),
        )
        db.add(tx)
        db.flush()

        audit = TransactionAuditLog(
            id=str(uuid.uuid4()),
            transaction_id=tx_id,
            shop_process_id=shop_process_id,
            previous_status=None,
            new_status=TransactionStatus.PENDING.value,
            reason="Catastro QR code generated",
            actor=req.user_id or "system",
            details={"expires_at": expires_at.isoformat(), "amount": str(amount_dec)},
        )
        db.add(audit)
        db.commit()
        db.refresh(tx)

        duration = time.time() - start_time
        metrics.record_transaction(TransactionStatus.PENDING.value, PaymentMethod.CATASTRO_QR.value, duration)

        return CatastroQrGenerateResponse(
            shop_process_id=shop_process_id,
            qr_payload=qr_payload,
            qr_image_data_uri=qr_image_uri,
            status=tx.status,
            amount=tx.amount,
            currency=tx.currency,
            expires_at=expires_at,
        )

    def get_qr_status(self, db: Session, shop_process_id: int) -> CatastroQrStatusResponse:
        tx = (
            db.query(BancardTransaction)
            .filter(BancardTransaction.shop_process_id == shop_process_id)
            .first()
        )
        if not tx:
            raise ValueError(f"QR transaction {shop_process_id} not found")

        # Check expiration if still pending
        if tx.status == TransactionStatus.PENDING.value and tx.expires_at:
            now = datetime.now(timezone.utc)
            # Ensure timezone awareness for comparison
            exp = tx.expires_at if tx.expires_at.tzinfo else tx.expires_at.replace(tzinfo=timezone.utc)
            if now > exp:
                tx.status = TransactionStatus.REJECTED.value
                tx.response_code = "EXPIRED"
                tx.response_description = "QR code expired prior to payment scan"
                db.commit()
                db.refresh(tx)

        return CatastroQrStatusResponse(
            shop_process_id=tx.shop_process_id,
            status=tx.status,
            amount=tx.amount,
            currency=tx.currency,
            payment_method=tx.payment_method,
            ticket_number=tx.ticket_number,
            authorization_number=tx.authorization_number,
            updated_at=tx.updated_at,
        )


service = BancardPaymentService()
