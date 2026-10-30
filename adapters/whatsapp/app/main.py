"""FastAPI service for the VibeCore WhatsApp Cloud API Adapter."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status

from app.client import (
    WhatsAppApiError,
    WhatsAppCloudApiClient,
    WhatsAppTimeoutError,
)
from app.config import settings
from app.otp import OtpManager, otp_manager
from app.schemas import (
    HealthResponse,
    OtpGenerateRequest,
    OtpGenerateResponse,
    OtpVerifyRequest,
    OtpVerifyResponse,
    ReadinessResponse,
    SendResponse,
    SendTemplateRequest,
    WebhookEventAck,
)
from app.webhook import (
    WebhookSecurityError,
    process_webhook_payload,
    verify_hub_challenge,
    verify_meta_signature,
)

app = FastAPI(
    title="VibeCore WhatsApp Cloud API Adapter",
    version="0.1.0",
    description="Slim Meta WhatsApp Cloud API microservice for OTP verification and template notifications.",
)


def get_whatsapp_client() -> WhatsAppCloudApiClient:
    return WhatsAppCloudApiClient(config=settings)


def get_otp_manager() -> OtpManager:
    return otp_manager


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Liveness check for container orchestrators."""
    return HealthResponse(status="healthy", service="vibecore-whatsapp-adapter")


@app.get("/ready", response_model=ReadinessResponse, tags=["system"])
def ready() -> ReadinessResponse:
    """Readiness check validating runtime configuration."""
    checks = {
        "phone_number_id": bool(settings.meta_phone_number_id),
        "access_token": bool(settings.get_access_token()),
        "app_secret": bool(settings.get_app_secret()),
        "webhook_verify_token": bool(settings.get_webhook_verify_token()),
    }
    return ReadinessResponse(
        status="ready" if all(checks.values()) else "not_ready",
        checks=checks,
    )


@app.get("/api/v1/webhook", tags=["webhook"])
def meta_webhook_verification(
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> Response:
    """Handle Meta's subscription challenge verification."""
    expected_token = settings.get_webhook_verify_token()
    try:
        challenge = verify_hub_challenge(
            mode=hub_mode,
            verify_token=hub_verify_token,
            challenge=hub_challenge,
            expected_token=expected_token,
        )
    except WebhookSecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return Response(content=challenge, media_type="text/plain")


@app.post("/api/v1/webhook", response_model=WebhookEventAck, tags=["webhook"])
async def meta_webhook_event(
    request: Request,
    x_hub_signature_256: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
) -> WebhookEventAck:
    """Receive and process incoming messages and delivery status updates from Meta."""
    raw_body = await request.body()
    app_secret = settings.get_app_secret()

    try:
        verify_meta_signature(
            raw_body=raw_body,
            signature_header=x_hub_signature_256,
            app_secret=app_secret,
        )
    except WebhookSecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON body",
        ) from exc

    return process_webhook_payload(payload)


@app.post(
    "/api/v1/messages/send-template",
    response_model=SendResponse,
    tags=["messaging"],
)
async def send_template_message(
    payload: SendTemplateRequest,
    client: WhatsAppCloudApiClient = Depends(get_whatsapp_client),
) -> SendResponse:
    """Send a pre-approved template message via Meta WhatsApp Cloud API."""
    try:
        return await client.send_template(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except WhatsAppTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=exc.message,
        ) from exc
    except WhatsAppApiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc


@app.post(
    "/api/v1/otp/send",
    response_model=OtpGenerateResponse,
    tags=["otp"],
)
async def send_otp_code(
    payload: OtpGenerateRequest,
    manager: OtpManager = Depends(get_otp_manager),
    client: WhatsAppCloudApiClient = Depends(get_whatsapp_client),
) -> OtpGenerateResponse:
    """Generate a cryptographically secure OTP and transmit it via WhatsApp Cloud API."""
    try:
        code, record = manager.create_otp(
            phone_number=payload.phone_number,
            purpose=payload.purpose,
            expiry_seconds=payload.expiry_seconds,
        )
    except ValueError as exc:
        msg = str(exc)
        code_status = (
            status.HTTP_429_TOO_MANY_REQUESTS
            if "Rate limited" in msg
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code_status, detail=msg) from exc

    try:
        res = await client.send_otp(
            to=record.phone_number,
            code=code,
            template_name=payload.template_name,
            language_code=payload.language_code,
            meta=payload.meta,
            custom_data=payload.custom_data,
        )
    except WhatsAppTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=exc.message,
        ) from exc
    except WhatsAppApiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc

    return OtpGenerateResponse(
        success=True,
        reference_id=record.reference_id,
        phone_number=record.phone_number,
        expires_at=record.expires_at,
        whatsapp_message_id=res.message_id,
        meta=payload.meta,
        custom_data=payload.custom_data,
    )


@app.post(
    "/api/v1/otp/verify",
    response_model=OtpVerifyResponse,
    tags=["otp"],
)
def verify_otp_code(
    payload: OtpVerifyRequest,
    manager: OtpManager = Depends(get_otp_manager),
) -> OtpVerifyResponse:
    """Validate a submitted OTP code against active sessions."""
    try:
        result = manager.verify_otp(
            phone_number=payload.phone_number,
            code=payload.code,
            purpose=payload.purpose,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    result.meta = payload.meta
    result.custom_data = payload.custom_data
    return result
