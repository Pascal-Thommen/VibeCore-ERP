"""
FastAPI route definitions for Pagopar Payment Gateway Adapter.
Exposes REST endpoints for order initiation, webhook notifications, and polling status sync.
"""

import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from pagopar.client import (
    PagoparGatewayError,
    PagoparNetworkTimeoutError,
    PagoparOrderNotFoundError,
    PagoparSignatureError,
)
from pagopar.config import settings
from pagopar.database import get_db
from pagopar.models import (
    CreateOrderRequest,
    OrderResponse,
    PagoparWebhookPayload,
    SyncOrderResponse,
    WebhookProcessResult,
)
from pagopar.service import PagoparPaymentService

logger = logging.getLogger("pagopar.router")

router = APIRouter(prefix="/api/v1/pagopar", tags=["Pagopar Payments"])
service = PagoparPaymentService()


def verify_adapter_auth(
    x_adapter_key: Optional[str] = Header(None, alias="X-Adapter-Key"),
    authorization: Optional[str] = Header(None),
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
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate Pagopar payment order and generate checkout URL",
)
async def create_order(
    request: CreateOrderRequest,
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID"),
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_adapter_auth),
) -> OrderResponse:
    try:
        return await service.create_payment_order(
            db=db,
            request=request,
            idempotency_key=x_idempotency_key,
            correlation_id=x_correlation_id,
        )
    except (PagoparNetworkTimeoutError, PagoparGatewayError) as exc:
        logger.error("Failed to create order %s: %s", request.order_id, exc)
        status_code = status.HTTP_504_GATEWAY_TIMEOUT if isinstance(exc, PagoparNetworkTimeoutError) else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error in create_order: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal adapter error: {exc}",
        ) from exc


@router.get(
    "/orders/{order_id}",
    response_model=OrderResponse,
    summary="Retrieve Pagopar order status and details",
)
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_adapter_auth),
) -> OrderResponse:
    try:
        return service.get_order_by_id(db=db, order_id=order_id)
    except PagoparOrderNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/orders/{order_id}/sync",
    response_model=SyncOrderResponse,
    summary="Actively poll and synchronize order payment status",
)
async def sync_order(
    order_id: str,
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-ID"),
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_adapter_auth),
) -> SyncOrderResponse:
    try:
        return await service.sync_order_status(db=db, order_id=order_id, correlation_id=x_correlation_id)
    except PagoparOrderNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (PagoparNetworkTimeoutError, PagoparGatewayError) as exc:
        logger.error("Polling synchronization error for order %s: %s", order_id, exc)
        status_code = status.HTTP_504_GATEWAY_TIMEOUT if isinstance(exc, PagoparNetworkTimeoutError) else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Public callback endpoint for Pagopar payment notifications",
)
async def handle_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """
    Receives raw Pagopar webhook, validates cryptographic SHA-1 signature,
    and idempotently records payment confirmation.
    """
    raw_body = await request.body()
    try:
        body_text = raw_body.decode("utf-8")
        data = json.loads(body_text)
        payload = PagoparWebhookPayload.model_validate(data)
    except Exception as exc:
        logger.warning("Malformed webhook payload received: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed webhook JSON: {exc}",
        ) from exc

    try:
        result: WebhookProcessResult = service.process_webhook(
            db=db,
            payload=payload,
            raw_payload_str=body_text,
        )
        # Pagopar documentation recommends returning the received body or success response
        return Response(
            content=json.dumps({"respuesta": True, "resultado": result.items}),
            media_type="application/json",
            status_code=status.HTTP_200_OK,
        )
    except PagoparSignatureError as exc:
        logger.error("Rejecting webhook due to invalid signature: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Webhook signature verification failed",
        ) from exc
    except Exception as exc:
        logger.exception("Error processing webhook: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook handling error: {exc}",
        ) from exc
