"""Typed client for Stripe Payment Gateway Adapter."""

from __future__ import annotations

from typing import Any

import httpx

from vibecore._base import BaseHttpClient
from vibecore.payments.stripe.models import (
    CreateCheckoutSessionRequest,
    CreatePaymentIntentRequest,
    PaymentResponse,
    SyncPaymentResponse,
)


class StripeClient(BaseHttpClient):
    """Client for Stripe international credit card and payments microservice."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {}
        if api_key:
            headers["X-Adapter-Key"] = api_key

        super().__init__(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            max_retries=max_retries,
            transport=transport,
        )

    def health(self) -> dict[str, Any]:
        """Liveness check for Stripe adapter."""
        resp = self._request("GET", "/health")
        self._raise_for_status(resp, adapter_type="stripe")
        return resp.json()

    def ready(self) -> dict[str, Any]:
        """Readiness probe for Stripe adapter."""
        resp = self._request("GET", "/ready")
        self._raise_for_status(resp, adapter_type="stripe")
        return resp.json()

    def create_checkout_session(
        self,
        request: CreateCheckoutSessionRequest | dict[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> PaymentResponse:
        """
        Create a Stripe Checkout Session and obtain the customer redirect URL.
        """
        req_obj = (
            request
            if isinstance(request, CreateCheckoutSessionRequest)
            else CreateCheckoutSessionRequest.model_validate(request)
        )
        headers = {}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        resp = self._request(
            "POST",
            "/api/v1/stripe/checkout-sessions",
            json=req_obj.model_dump(mode="json", exclude_none=True),
            headers=headers if headers else None,
        )
        self._raise_for_status(resp, adapter_type="stripe")
        return PaymentResponse.model_validate(resp.json())

    def create_payment_intent(
        self,
        request: CreatePaymentIntentRequest | dict[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> PaymentResponse:
        """
        Create a direct Stripe PaymentIntent.
        """
        req_obj = (
            request
            if isinstance(request, CreatePaymentIntentRequest)
            else CreatePaymentIntentRequest.model_validate(request)
        )
        headers = {}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        resp = self._request(
            "POST",
            "/api/v1/stripe/payment-intents",
            json=req_obj.model_dump(mode="json", exclude_none=True),
            headers=headers if headers else None,
        )
        self._raise_for_status(resp, adapter_type="stripe")
        return PaymentResponse.model_validate(resp.json())

    def get_payment(self, payment_id: str) -> PaymentResponse:
        """
        Retrieve Stripe transaction status and details by payment ID.
        """
        resp = self._request("GET", f"/api/v1/stripe/payments/{payment_id}")
        self._raise_for_status(resp, adapter_type="stripe")
        return PaymentResponse.model_validate(resp.json())

    def sync_payment(
        self,
        payment_id: str,
        *,
        correlation_id: str | None = None,
    ) -> SyncPaymentResponse:
        """
        Actively poll and synchronize payment status with the Stripe API.
        """
        headers = {}
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        resp = self._request(
            "POST",
            f"/api/v1/stripe/payments/{payment_id}/sync",
            headers=headers if headers else None,
        )
        self._raise_for_status(resp, adapter_type="stripe")
        return SyncPaymentResponse.model_validate(resp.json())
