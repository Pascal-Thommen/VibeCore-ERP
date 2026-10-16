"""FastAPI application for VibeCore Pay Bancard vPOS 2.0 & Catastro QR Microservice."""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from bancard.client import BancardGatewayError
from bancard.config import settings
from bancard.constants import HEADER_CORRELATION_ID, HEADER_IDEMPOTENCY_KEY, TransactionStatus
from bancard.database import BancardTransaction, DeadLetterWebhook, get_db, init_db
from bancard.metrics import metrics
from bancard.models import (
    AuditLogEntry,
    BancardWebhookPayload,
    BancardWebhookResponse,
    CardCatastroRequest,
    CardCatastroResponse,
    CatastroQrGenerateRequest,
    CatastroQrGenerateResponse,
    CatastroQrStatusResponse,
    DeadLetterItem,
    HealthResponse,
    RollbackRequest,
    RollbackResponse,
    SingleBuyInitRequest,
    SingleBuyInitResponse,
    TokenChargeRequest,
    TokenChargeResponse,
    TransactionDetailResponse,
)
from bancard.service import service
from bancard.webhook_dispatcher import dispatcher

logger = logging.getLogger("bancard.app")

app = FastAPI(
    title="VibeCore Pay: Bancard vPOS & Catastro QR Adapter API",
    version=settings.service_version,
    description="Enterprise microservice for Paraguayan payment processing via Bancard vPOS 2.0, card tokenization, and dynamic EMVCo Catastro QR in Guaranies (PYG).",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    init_db()


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    corr_id = request.headers.get(HEADER_CORRELATION_ID) or f"corr_{uuid.uuid4().hex[:12]}"
    response = await call_next(request)
    response.headers[HEADER_CORRELATION_ID] = corr_id
    return response


# --- Observability & Health ---


@app.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Liveness and Readiness Probe",
    tags=["Observability"],
)
@app.get(
    "/health",
    response_model=HealthResponse,
    include_in_schema=False,
)
@app.get(
    "/ready",
    response_model=HealthResponse,
    include_in_schema=False,
)
def healthz(db: Session = Depends(get_db)):
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"unhealthy: {str(exc)}"

    pending_count = (
        db.query(BancardTransaction)
        .filter(BancardTransaction.status == TransactionStatus.PENDING.value)
        .count()
    )
    dl_count = (
        db.query(DeadLetterWebhook)
        .filter(DeadLetterWebhook.status == "FAILED")
        .count()
    )

    is_healthy = db_status == "connected"
    return HealthResponse(
        status="healthy" if is_healthy else "degraded",
        service=settings.service_name,
        version=settings.service_version,
        database=db_status,
        environment=settings.bancard_environment.value,
        pending_transactions_count=pending_count,
        dead_letter_count=dl_count,
    )


@app.get(
    "/metrics",
    summary="Prometheus Metrics Exposition",
    tags=["Observability"],
)
def get_metrics():
    content = metrics.generate_prometheus_text()
    return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")


# --- Bancard vPOS 2.0 Payment Endpoints ---


@app.post(
    "/api/v1/payments/single-buy",
    response_model=SingleBuyInitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize Single Buy Checkout",
    description="Generates Bancard vPOS 2.0 security token and process_id for embedded payment iframe or redirect.",
    tags=["vPOS Payments"],
)
def initialize_single_buy(
    req: SingleBuyInitRequest,
    idempotency_key: Optional[str] = Header(None, alias=HEADER_IDEMPOTENCY_KEY),
    db: Session = Depends(get_db),
):
    if idempotency_key and not req.idempotency_key:
        req.idempotency_key = idempotency_key

    try:
        return service.initialize_single_buy(db=db, req=req)
    except BancardGatewayError as ge:
        logger.error("Bancard gateway error during single_buy: %s", str(ge))
        raise HTTPException(status_code=ge.status_code, detail=str(ge))
    except Exception as exc:
        logger.exception("Failed to initialize single_buy: %s", str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@app.post(
    "/api/v1/payments/cards/new",
    response_model=CardCatastroResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize Card Catastro (Registration)",
    description="Requests a secure process token to render the Bancard card tokenization iframe.",
    tags=["Card Catastro"],
)
def initialize_cards_new(
    req: CardCatastroRequest,
    db: Session = Depends(get_db),
):
    try:
        return service.initialize_card_catastro(db=db, req=req)
    except BancardGatewayError as ge:
        logger.error("Bancard gateway error during cards_new: %s", str(ge))
        raise HTTPException(status_code=ge.status_code, detail=str(ge))
    except Exception as exc:
        logger.exception("Failed to initialize cards_new: %s", str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@app.post(
    "/api/v1/payments/charge",
    response_model=TokenChargeResponse,
    summary="Execute Tokenized Card Charge",
    description="Charges a pre-registered card alias token for 1-click or recurring subscription billing.",
    tags=["vPOS Payments"],
)
def execute_token_charge(
    req: TokenChargeRequest,
    idempotency_key: Optional[str] = Header(None, alias=HEADER_IDEMPOTENCY_KEY),
    db: Session = Depends(get_db),
):
    if idempotency_key and not req.idempotency_key:
        req.idempotency_key = idempotency_key

    try:
        return service.execute_token_charge(db=db, req=req)
    except BancardGatewayError as ge:
        logger.error("Bancard gateway error during token charge: %s", str(ge))
        raise HTTPException(status_code=ge.status_code, detail=str(ge))
    except Exception as exc:
        logger.exception("Failed to execute token charge: %s", str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@app.post(
    "/api/v1/payments/{shop_process_id}/rollback",
    response_model=RollbackResponse,
    summary="Rollback / Cancel Payment",
    description="Reverses an authorized or pending transaction with Bancard and updates audit trail.",
    tags=["vPOS Payments"],
)
def rollback_payment(
    shop_process_id: int,
    req: RollbackRequest = RollbackRequest(),
    db: Session = Depends(get_db),
):
    try:
        return service.execute_rollback(db=db, shop_process_id=shop_process_id, reason=req.reason)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except BancardGatewayError as ge:
        logger.error("Bancard gateway rollback rejected or failed: %s", str(ge))
        raise HTTPException(status_code=ge.status_code, detail=str(ge))
    except Exception as exc:
        logger.exception("Failed to execute rollback: %s", str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@app.get(
    "/api/v1/payments/{shop_process_id}",
    response_model=TransactionDetailResponse,
    summary="Get Transaction & Audit Trail",
    tags=["vPOS Payments"],
)
def get_transaction(
    shop_process_id: int,
    db: Session = Depends(get_db),
):
    tx = (
        db.query(BancardTransaction)
        .filter(BancardTransaction.shop_process_id == shop_process_id)
        .first()
    )
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Transaction {shop_process_id} not found")

    audit_logs = [
        AuditLogEntry(
            id=log.id,
            previous_status=log.previous_status,
            new_status=log.new_status,
            reason=log.reason,
            actor=log.actor,
            created_at=log.created_at,
        )
        for log in tx.audit_logs
    ]

    return TransactionDetailResponse(
        id=tx.id,
        shop_process_id=tx.shop_process_id,
        idempotency_key=tx.idempotency_key,
        user_id=tx.user_id,
        amount=tx.amount,
        currency=tx.currency,
        payment_method=tx.payment_method,
        status=tx.status,
        description=tx.description,
        response_code=tx.response_code,
        response_description=tx.response_description,
        ticket_number=tx.ticket_number,
        authorization_number=tx.authorization_number,
        created_at=tx.created_at,
        updated_at=tx.updated_at,
        audit_logs=audit_logs,
    )


# --- Bancard Webhook Confirmation Receiver ---


@app.post(
    "/api/v1/payments/webhook/bancard",
    response_model=BancardWebhookResponse,
    summary="Bancard Confirmation Callback",
    description="Processes server-to-server webhook confirmation from Bancard vPOS. Validates security token and dispatches signed events.",
    tags=["Webhooks"],
)
def bancard_confirmation_webhook(
    payload: BancardWebhookPayload,
    db: Session = Depends(get_db),
):
    try:
        return service.process_bancard_confirmation(db=db, payload=payload)
    except ValueError as ve:
        logger.error("Bancard webhook verification failure: %s", str(ve))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(ve))
    except Exception as exc:
        logger.exception("Bancard webhook processing error: %s", str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# --- Paraguay Catastro QR Endpoints ---


@app.post(
    "/api/v1/qr/generate",
    response_model=CatastroQrGenerateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate Dynamic Catastro QR (PYG)",
    description="Constructs an EMVCo dynamic QR code for Paraguay in Guaranies (PYG) with CRC16 and Base64 PNG image.",
    tags=["Catastro QR"],
)
def generate_catastro_qr(
    req: CatastroQrGenerateRequest,
    idempotency_key: Optional[str] = Header(None, alias=HEADER_IDEMPOTENCY_KEY),
    db: Session = Depends(get_db),
):
    if idempotency_key and not req.idempotency_key:
        req.idempotency_key = idempotency_key

    try:
        return service.generate_catastro_qr(db=db, req=req)
    except Exception as exc:
        logger.exception("Failed to generate QR: %s", str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@app.get(
    "/api/v1/qr/{shop_process_id}/status",
    response_model=CatastroQrStatusResponse,
    summary="Poll Catastro QR Status",
    description="Queries transaction status for clients polling dynamic QR payments.",
    tags=["Catastro QR"],
)
def get_qr_status(
    shop_process_id: int,
    db: Session = Depends(get_db),
):
    try:
        return service.get_qr_status(db=db, shop_process_id=shop_process_id)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as exc:
        logger.exception("Error checking QR status: %s", str(exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# --- Dead Letter Queue Inspection & Reprocessing ---


@app.get(
    "/api/v1/webhooks/dead-letter",
    response_model=List[DeadLetterItem],
    summary="List Dead-Letter Webhooks",
    description="Lists un-deliverable outbound webhooks queued after exhausted retries.",
    tags=["Resilience"],
)
def list_dead_letters(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    items = (
        db.query(DeadLetterWebhook)
        .order_by(DeadLetterWebhook.created_at.desc())
        .limit(limit)
        .all()
    )
    return items


@app.post(
    "/api/v1/webhooks/dead-letter/{dead_letter_id}/retry",
    summary="Retry Dead-Letter Delivery",
    tags=["Resilience"],
)
def retry_dead_letter(
    dead_letter_id: str,
    db: Session = Depends(get_db),
):
    success = dispatcher.retry_dead_letter(db=db, dead_letter_id=dead_letter_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Retry attempt failed or dead-letter item not in FAILED status.",
        )
    return {"status": "success", "dead_letter_id": dead_letter_id, "message": "Reprocessed successfully"}
