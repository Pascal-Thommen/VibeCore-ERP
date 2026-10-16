"""
FastAPI route definitions for Stripe Payment Gateway Adapter.
Exposes REST endpoints for checkout sessions, direct payment intents, webhook notifications, and sync polling.
"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from stripe_adapter.client import (
    StripeGatewayError,
    StripeNetworkTimeoutError,
    StripeOrderNotFoundError,
    StripeSignatureError,
)
from stripe_adapter.config import settings
from stripe_adapter.database import get_db
from stripe_adapter.models import (
    CreateCheckoutSessionRequest,
    CreatePaymentIntentRequest,
    PaymentResponse,
    SyncPaymentResponse,
    WebhookProcessResult,
)
from stripe_adapter.service import StripePaymentService

logger = logging.getLogger("stripe_adapter.router")

router = APIRouter(prefix="/api/v1/stripe", tags=["Stripe Payments"])
service = StripePaymentService()


def verify_adapter_auth(
    x_adapter_key: str | None = Header(None, alias="X-Adapter-Key"),
    authorization: str | None = Header(None),
) -> None:
    """Verifies internal adapter authentication if ADAPTER_API_KEY is configured."""
    if not settings.adapter_api_key:
        return

    expected = settings.adapter_api_key
    if x_adapter_key == expected:
        return

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
        if token == expected:
            return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized adapter request. Invalid or missing API key.",
    )


@router.post(
    "/checkout-sessions",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Stripe Checkout Session and obtain redirect URL",
)
async def create_checkout_session(
    request: CreateCheckoutSessionRequest,
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_adapter_auth),
) -> PaymentResponse:
    try:
        return await service.create_checkout_session(
            db=db,
            request=request,
            idempotency_key=x_idempotency_key,
            correlation_id=x_correlation_id,
        )
    except (StripeNetworkTimeoutError, StripeGatewayError) as exc:
        logger.error("Failed to create checkout session for order %s: %s", request.order_id, exc)
        status_code = status.HTTP_504_GATEWAY_TIMEOUT if isinstance(exc, StripeNetworkTimeoutError) else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error in create_checkout_session: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal adapter error: {exc}",
        ) from exc


@router.post(
    "/payment-intents",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create direct Stripe PaymentIntent",
)
async def create_payment_intent(
    request: CreatePaymentIntentRequest,
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_adapter_auth),
) -> PaymentResponse:
    try:
        return await service.create_payment_intent(
            db=db,
            request=request,
            idempotency_key=x_idempotency_key,
            correlation_id=x_correlation_id,
        )
    except (StripeNetworkTimeoutError, StripeGatewayError) as exc:
        logger.error("Failed to create payment intent for order %s: %s", request.order_id, exc)
        status_code = status.HTTP_504_GATEWAY_TIMEOUT if isinstance(exc, StripeNetworkTimeoutError) else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error in create_payment_intent: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal adapter error: {exc}",
        ) from exc


@router.get(
    "/payments/{payment_id}",
    response_model=PaymentResponse,
    summary="Retrieve Stripe transaction status and details",
)
def get_payment(
    payment_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_adapter_auth),
) -> PaymentResponse:
    try:
        return service.get_payment_by_id(db=db, payment_id=payment_id)
    except StripeOrderNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/payments/{payment_id}/sync",
    response_model=SyncPaymentResponse,
    summary="Actively poll and synchronize payment status with Stripe",
)
async def sync_payment(
    payment_id: str,
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_adapter_auth),
) -> SyncPaymentResponse:
    try:
        return await service.sync_payment_status(db=db, payment_id=payment_id, correlation_id=x_correlation_id)
    except StripeOrderNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (StripeNetworkTimeoutError, StripeGatewayError) as exc:
        logger.error("Polling sync error for payment %s: %s", payment_id, exc)
        status_code = status.HTTP_504_GATEWAY_TIMEOUT if isinstance(exc, StripeNetworkTimeoutError) else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post(
    "/webhook",
    response_model=WebhookProcessResult,
    status_code=status.HTTP_200_OK,
    summary="Public callback endpoint for Stripe payment notifications",
)
async def handle_webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
) -> WebhookProcessResult:
    """
    Receives raw Stripe webhook, validates HMAC-SHA256 cryptographic signature,
    and idempotently records payment confirmation.
    """
    raw_body = await request.body()
    try:
        return service.process_webhook(
            db=db,
            raw_body=raw_body,
            signature_header=stripe_signature,
        )
    except StripeSignatureError as exc:
        logger.error("Rejecting Stripe webhook due to invalid signature: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error processing Stripe webhook: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook handling error: {exc}",
        ) from exc
