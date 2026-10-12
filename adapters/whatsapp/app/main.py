"""FastAPI service for the VibeCore WhatsApp Cloud API Adapter."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel

from app.client import (
    ServiceWindowExpiredError,
    WhatsAppApiError,
    WhatsAppCloudApiClient,
    whatsapp_client,
)
from app.config import settings
from app.otp import OtpManager, otp_manager
from app.schemas import (
    OtpGenerateRequest,
    OtpGenerateResponse,
    OtpVerifyRequest,
    OtpVerifyResponse,
    SendResponse,
    SendTemplateRequest,
    SendTextRequest,
    ServiceWindowStatus,
    WebhookEventAck,
)
from app.service_window import ServiceWindowManager, service_window_manager
from app.webhook import (
    WebhookSecurityError,
    process_webhook_payload,
    verify_hub_challenge,
    verify_meta_signature,
)

app = FastAPI(
    title="VibeCore WhatsApp Cloud API Adapter",
    version="0.1.0",
    description="Meta WhatsApp Cloud API adapter for single sign-on OTP and messaging.",
)


class HealthResponse(BaseModel):
    status: str
    adapter: str = "whatsapp-cloud-api"
    test_mode: bool


@app.get("/health", response_model=HealthResponse, tags=["system"])
@app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Liveness check for container orchestrators."""
    return HealthResponse(
        status="ok",
        adapter="whatsapp-cloud-api",
        test_mode=settings.meta_test_mode,
    )


@app.get("/ready", response_model=HealthResponse, tags=["system"])
@app.get("/api/v1/ready", response_model=HealthResponse, tags=["system"])
def ready() -> HealthResponse:
    """Readiness check validating runtime configuration."""
    return HealthResponse(
        status="ready",
        adapter="whatsapp-cloud-api",
        test_mode=settings.meta_test_mode,
    )


# Webhook Endpoints
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

    # Validate HMAC signature if app_secret is configured
    if app_secret:
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


# Messaging Endpoints
@app.post(
    "/api/v1/messages/send-template",
    response_model=SendResponse,
    tags=["messaging"],
)
def send_template_message(
    payload: SendTemplateRequest,
    client: WhatsAppCloudApiClient = Depends(lambda: whatsapp_client),
) -> SendResponse:
    """Send a pre-approved template message via Meta WhatsApp Cloud API."""
    try:
        return client.send_template(payload)
    except WhatsAppApiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/v1/messages/send-text",
    response_model=SendResponse,
    tags=["messaging"],
)
def send_text_message(
    payload: SendTextRequest,
    client: WhatsAppCloudApiClient = Depends(lambda: whatsapp_client),
) -> SendResponse:
    """Send a free-form text message inside the Meta 24-hour customer service window."""
    try:
        return client.send_text(payload)
    except ServiceWindowExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except WhatsAppApiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc


# OTP / SSO Authentication Endpoints
@app.post(
    "/api/v1/otp/send",
    response_model=OtpGenerateResponse,
    tags=["otp"],
)
def send_otp_code(
    payload: OtpGenerateRequest,
    manager: OtpManager = Depends(lambda: otp_manager),
    client: WhatsAppCloudApiClient = Depends(lambda: whatsapp_client),
) -> OtpGenerateResponse:
    """Generate a cryptographically secure OTP and transmit it via WhatsApp."""
    try:
        code, record = manager.create_otp(
            phone_number=payload.phone_number,
            purpose=payload.purpose,
            expiry_seconds=payload.expiry_seconds,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc

    whatsapp_message_id = None
    if payload.send_via_whatsapp:
        try:
            res = client.send_otp(
                to=payload.phone_number,
                code=code,
                meta=payload.meta,
                custom_data=payload.custom_data,
            )
            whatsapp_message_id = res.message_id
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to transmit OTP via WhatsApp: {exc}",
            ) from exc

    expose_code = code if settings.meta_test_mode or settings.app_env != "production" else None

    return OtpGenerateResponse(
        success=True,
        reference_id=record.reference_id,
        phone_number=record.phone_number,
        expires_at=record.expires_at,
        whatsapp_message_id=whatsapp_message_id,
        test_code=expose_code,
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
    manager: OtpManager = Depends(lambda: otp_manager),
) -> OtpVerifyResponse:
    """Validate a submitted OTP code against active sessions."""
    result = manager.verify_otp(
        phone_number=payload.phone_number,
        code=payload.code,
        purpose=payload.purpose,
    )
    result.meta = payload.meta
    result.custom_data = payload.custom_data
    return result


# Service Window Status
@app.get(
    "/api/v1/service-window/{phone_number}",
    response_model=ServiceWindowStatus,
    tags=["service-window"],
)
def get_service_window_status(
    phone_number: str,
    window_mgr: ServiceWindowManager = Depends(lambda: service_window_manager),
) -> ServiceWindowStatus:
    """Query current status of the 24-hour customer service window for a contact."""
    return window_mgr.get_window_status(phone_number)
