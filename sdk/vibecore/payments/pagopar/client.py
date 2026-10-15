"""Typed client for Pagopar Payment Gateway Adapter."""

from __future__ import annotations

from typing import Any

import httpx

from vibecore._base import BaseHttpClient
from vibecore.payments.pagopar.models import (
    CreateOrderRequest,
    OrderResponse,
    SyncOrderResponse,
)


class PagoparClient(BaseHttpClient):
    """Client for Pagopar Paraguayan payment gateway microservice."""

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
        """Liveness check for Pagopar adapter."""
        resp = self._request("GET", "/health")
        self._raise_for_status(resp, adapter_type="pagopar")
        return resp.json()

    def ready(self) -> dict[str, Any]:
        """Readiness probe for Pagopar adapter."""
        resp = self._request("GET", "/ready")
        self._raise_for_status(resp, adapter_type="pagopar")
        return resp.json()

    def create_order(
        self,
        request: CreateOrderRequest | dict[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> OrderResponse:
        """
        Initiate a Pagopar payment order and generate the checkout URL.
        """
        req_obj = (
            request
            if isinstance(request, CreateOrderRequest)
            else CreateOrderRequest.model_validate(request)
        )
        headers = {}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        resp = self._request(
            "POST",
            "/api/v1/pagopar/orders",
            json=req_obj.model_dump(mode="json", exclude_none=True),
            headers=headers if headers else None,
        )
        self._raise_for_status(resp, adapter_type="pagopar")
        return OrderResponse.model_validate(resp.json())

    def get_order(self, order_id: str) -> OrderResponse:
        """
        Retrieve Pagopar payment order status and details by order ID.
        """
        resp = self._request("GET", f"/api/v1/pagopar/orders/{order_id}")
        self._raise_for_status(resp, adapter_type="pagopar")
        return OrderResponse.model_validate(resp.json())

    def sync_order(
        self,
        order_id: str,
        *,
        correlation_id: str | None = None,
    ) -> SyncOrderResponse:
        """
        Actively poll and synchronize payment status from the Pagopar gateway.
        """
        headers = {}
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        resp = self._request(
            "POST",
            f"/api/v1/pagopar/orders/{order_id}/sync",
            headers=headers if headers else None,
        )
        self._raise_for_status(resp, adapter_type="pagopar")
        return SyncOrderResponse.model_validate(resp.json())
