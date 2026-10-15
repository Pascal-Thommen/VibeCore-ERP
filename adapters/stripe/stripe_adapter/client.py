"""
HTTP Client for Stripe REST API v1.
Includes cryptographic HMAC-SHA256 signature generation and verification,
currency cent conversion, explicit timeouts, and exponential backoff retry management.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import httpx

from stripe_adapter.config import Settings, settings
from stripe_adapter.models import (
    CreateCheckoutSessionRequest,
    CreatePaymentIntentRequest,
    CurrencyHelper,
)

logger = logging.getLogger("stripe_adapter.client")


class StripeError(Exception):
    """Base exception for all Stripe adapter operations."""
    pass


class StripeSignatureError(StripeError):
    """Raised when cryptographic webhook signature validation fails."""
    pass


class StripeGatewayError(StripeError):
    """Raised when Stripe gateway rejects a request or returns an error response."""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class StripeNetworkTimeoutError(StripeError):
    """Raised when Stripe network requests exceed configured timeouts."""
    pass


class StripeOrderNotFoundError(StripeError):
    """Raised when a requested order or payment is not found."""
    pass


class StripeClient:
    """Enterprise client for Stripe REST API operations."""

    def __init__(self, custom_settings: Optional[Settings] = None):
        self.cfg = custom_settings or settings

    @staticmethod
    def compute_webhook_signature(payload: bytes, secret: str, timestamp: int) -> str:
        """
        Computes expected HMAC-SHA256 signature for Stripe webhook payload:
        signature = HMAC-SHA256(secret, f"{timestamp}." + payload)
        """
        signed_payload = f"{timestamp}.".encode("utf-8") + payload
        return hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()

    @classmethod
    def verify_webhook_signature(
        cls,
        payload: bytes,
        signature_header: Optional[str],
        secret: str,
        tolerance: int = 300,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Verifies webhook authenticity using timing-safe comparison to prevent timing attacks.
        Validates timestamp against allowed tolerance to protect against replay attacks.
        Returns (is_valid, expected_signature, event_dict).
        """
        if not signature_header or not secret:
            logger.error("Missing signature header or webhook secret")
            return False, "", {}

        # Parse header: t=1492774577,v1=5257a869e7ecebeda32affa62cd496d1b9e67e47731ec2d599e773f577c39810
        timestamp: Optional[int] = None
        signatures: List[str] = []

        parts = signature_header.split(",")
        for item in parts:
            if "=" not in item:
                continue
            k, v = item.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k == "t":
                try:
                    timestamp = int(v)
                except ValueError:
                    logger.error("Invalid timestamp integer in Stripe-Signature: %s", v)
                    return False, "", {}
            elif k == "v1":
                signatures.append(v)

        if timestamp is None or not signatures:
            logger.error("Stripe-Signature header missing timestamp or v1 signature")
            return False, "", {}

        # Replay attack defense
        current_time = int(time.time())
        if abs(current_time - timestamp) > tolerance:
            logger.warning(
                "Webhook timestamp outside tolerance: current=%d header=%d diff=%d tolerance=%d",
                current_time,
                timestamp,
                abs(current_time - timestamp),
                tolerance,
            )
            return False, "", {}

        expected_sig = cls.compute_webhook_signature(payload, secret, timestamp)

        # Timing-safe comparison against all v1 signatures in header
        is_valid = any(hmac.compare_digest(expected_sig, sig) for sig in signatures)

        event_data: Dict[str, Any] = {}
        if is_valid:
            try:
                event_data = json.loads(payload.decode("utf-8"))
            except Exception as exc:
                logger.error("Webhook payload is not valid JSON: %s", exc)
                return False, expected_sig, {}

        return is_valid, expected_sig, event_data

    async def _request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes an HTTP request to Stripe REST API with exponential backoff and timeouts."""
        url = f"{self.cfg.resolved_base_url}{path}"
        req_headers = {
            "Authorization": f"Bearer {self.cfg.stripe_secret_key}",
            "Stripe-Version": "2024-06-20",
        }
        if headers:
            req_headers.update(headers)
        if correlation_id:
            req_headers["X-Correlation-ID"] = correlation_id

        last_error: Optional[Exception] = None
        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.cfg.request_timeout_seconds) as client:
                    logger.info("Calling Stripe REST API %s %s attempt=%d/%d", method, url, attempt, self.cfg.max_retries)
                    if method.upper() == "GET":
                        resp = await client.get(url, headers=req_headers)
                    elif method.upper() == "POST":
                        resp = await client.post(url, data=data, headers=req_headers)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")

                # Server error (5xx) -> retry with exponential backoff
                if resp.status_code >= 500:
                    logger.warning("Stripe server error status=%d body=%s", resp.status_code, resp.text)
                    if attempt < self.cfg.max_retries:
                        await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                        continue
                    raise StripeGatewayError(
                        f"Stripe server error ({resp.status_code}): {resp.text}",
                        status_code=resp.status_code,
                    )

                # Client rejection (4xx)
                if resp.status_code >= 400:
                    logger.error("Stripe rejection status=%d body=%s", resp.status_code, resp.text)
                    try:
                        err_json = resp.json()
                        err_msg = err_json.get("error", {}).get("message", resp.text)
                    except Exception:
                        err_msg = resp.text
                    raise StripeGatewayError(
                        f"Stripe rejected request ({resp.status_code}): {err_msg}",
                        status_code=resp.status_code,
                    )

                return resp.json()

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                logger.warning(
                    "Network error calling Stripe (attempt %d/%d): %s",
                    attempt,
                    self.cfg.max_retries,
                    exc,
                )
                last_error = exc
                if attempt < self.cfg.max_retries:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
                raise StripeNetworkTimeoutError(
                    f"Stripe connection timed out or failed after {self.cfg.max_retries} attempts: {exc}"
                ) from exc

        if last_error:
            raise StripeGatewayError(f"Stripe request failed: {last_error}") from last_error
        raise StripeGatewayError("Unexpected failure executing Stripe request")

    async def create_checkout_session(
        self,
        request: CreateCheckoutSessionRequest,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a hosted Stripe Checkout Session via POST /v1/checkout/sessions.
        Transforms amounts to smallest currency units (cents).
        """
        data: Dict[str, str] = {
            "mode": "payment",
            "customer_email": request.customer_email,
            "client_reference_id": request.order_id,
            "metadata[order_id]": request.order_id,
            "success_url": request.success_url or f"https://vibecore.erp/payments/success?order_id={request.order_id}",
            "cancel_url": request.cancel_url or f"https://vibecore.erp/payments/cancel?order_id={request.order_id}",
        }

        if request.items and len(request.items) > 0:
            for idx, it in enumerate(request.items):
                item_cur = (it.currency or request.currency).upper()
                item_cents = CurrencyHelper.amount_to_cents(it.amount, item_cur)
                data[f"line_items[{idx}][price_data][currency]"] = item_cur.lower()
                data[f"line_items[{idx}][price_data][unit_amount]"] = str(item_cents)
                data[f"line_items[{idx}][price_data][product_data][name]"] = it.name
                if it.description:
                    data[f"line_items[{idx}][price_data][product_data][description]"] = it.description
                data[f"line_items[{idx}][quantity]"] = str(it.quantity)
        else:
            total_cents = CurrencyHelper.amount_to_cents(request.amount_total, request.currency)
            data["line_items[0][price_data][currency]"] = request.currency.lower()
            data["line_items[0][price_data][unit_amount]"] = str(total_cents)
            data["line_items[0][price_data][product_data][name]"] = request.description
            data["line_items[0][quantity]"] = "1"

        if request.meta:
            for k, v in request.meta.items():
                data[f"metadata[{k}]"] = str(v)

        headers: Dict[str, str] = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        resp_data = await self._request(
            method="POST",
            path="/v1/checkout/sessions",
            data=data,
            headers=headers,
            correlation_id=correlation_id,
        )

        session_id = resp_data.get("id")
        checkout_url = resp_data.get("url")
        if not session_id or not checkout_url:
            raise StripeGatewayError("Stripe Checkout Session response missing 'id' or 'url'", details=resp_data)

        return {
            "session_id": session_id,
            "checkout_url": checkout_url,
            "payment_status": resp_data.get("payment_status", "unpaid"),
            "raw_response": resp_data,
        }

    async def create_payment_intent(
        self,
        request: CreatePaymentIntentRequest,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a direct PaymentIntent via POST /v1/payment_intents.
        """
        amount_cents = CurrencyHelper.amount_to_cents(request.amount, request.currency)
        data: Dict[str, str] = {
            "amount": str(amount_cents),
            "currency": request.currency.lower(),
            "description": request.description,
            "metadata[order_id]": request.order_id,
            "automatic_payment_methods[enabled]": "true",
        }
        if request.customer_email:
            data["receipt_email"] = request.customer_email
        if request.payment_method:
            data["payment_method"] = request.payment_method
            if request.confirm:
                data["confirm"] = "true"
                data["return_url"] = f"https://vibecore.erp/payments/complete?order_id={request.order_id}"

        if request.meta:
            for k, v in request.meta.items():
                data[f"metadata[{k}]"] = str(v)

        headers: Dict[str, str] = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        resp_data = await self._request(
            method="POST",
            path="/v1/payment_intents",
            data=data,
            headers=headers,
            correlation_id=correlation_id,
        )

        pi_id = resp_data.get("id")
        client_secret = resp_data.get("client_secret")
        if not pi_id:
            raise StripeGatewayError("Stripe PaymentIntent response missing 'id'", details=resp_data)

        return {
            "payment_intent_id": pi_id,
            "client_secret": client_secret,
            "status": resp_data.get("status", "requires_payment_method"),
            "raw_response": resp_data,
        }

    async def get_checkout_session(
        self,
        session_id: str,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieves a Checkout Session from Stripe."""
        return await self._request(
            method="GET",
            path=f"/v1/checkout/sessions/{session_id}",
            correlation_id=correlation_id,
        )

    async def get_payment_intent(
        self,
        payment_intent_id: str,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieves a PaymentIntent from Stripe."""
        return await self._request(
            method="GET",
            path=f"/v1/payment_intents/{payment_intent_id}",
            correlation_id=correlation_id,
        )
