"""
HTTP Client for Pagopar API v2 and v1.1 Polling.
Includes cryptographic token generation, timing-safe verification,
explicit timeouts, and exponential backoff retry management.
"""

import asyncio
import hashlib
import hmac
import logging
from typing import Any, Dict, List, Optional, Union
import httpx
from pagopar.config import Settings, settings
from pagopar.models import BuyerModel, OrderItemModel

logger = logging.getLogger("pagopar.client")


class PagoparError(Exception):
    """Base exception for all Pagopar adapter operations."""
    pass


class PagoparSignatureError(PagoparError):
    """Raised when cryptographic signature validation fails."""
    pass


class PagoparGatewayError(PagoparError):
    """Raised when the Pagopar gateway rejects a request or returns an error response."""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class PagoparNetworkTimeoutError(PagoparError):
    """Raised when Pagopar network requests exceed configured timeouts."""
    pass


class PagoparOrderNotFoundError(PagoparError):
    """Raised when a requested order is not found."""
    pass



class PagoparClient:
    """Enterprise client for Pagopar REST API operations."""

    def __init__(self, custom_settings: Optional[Settings] = None):
        self.cfg = custom_settings or settings

    @staticmethod
    def compute_order_token(private_key: str, order_id: Union[str, int], amount: Union[float, int]) -> str:
        """
        Computes SHA-1 hash for initiating a transaction:
        token = SHA1(private_key + id_pedido_comercio + str(float(monto_total)))
        """
        raw = f"{private_key}{order_id}{float(amount)}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_webhook_token(private_key: str, hash_pedido: str) -> str:
        """
        Computes expected SHA-1 hash for verifying webhook notifications:
        token = SHA1(private_key + hash_pedido)
        """
        raw = f"{private_key}{hash_pedido}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @classmethod
    def verify_webhook_signature(cls, private_key: str, hash_pedido: str, received_token: str) -> bool:
        """
        Verifies webhook authenticity using timing-safe comparison to prevent timing attacks.
        """
        if not received_token or not hash_pedido:
            return False
        expected_token = cls.compute_webhook_token(private_key, hash_pedido)
        return hmac.compare_digest(expected_token.lower(), received_token.lower())

    @staticmethod
    def compute_polling_token(private_key: str) -> str:
        """
        Computes SHA-1 hash for polling order status:
        token = SHA1(private_key + 'CONSULTA')
        """
        raw = f"{private_key}CONSULTA"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    async def initiate_transaction(
        self,
        order_id: str,
        monto_total: float,
        description: str,
        buyer: BuyerModel,
        items: List[OrderItemModel],
        fecha_maxima_pago: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initiates a transaction via Pagopar API v2 POST /api/comercios/2.0/iniciar-transaccion.
        Applies exponential backoff retries on transient connection failures.
        """
        url = f"{self.cfg.resolved_base_url}/api/comercios/2.0/iniciar-transaccion"
        token = self.compute_order_token(self.cfg.pagopar_private_key, order_id, monto_total)

        formatted_items = []
        for it in items:
            formatted_items.append({
                "id_producto": str(it.id_producto),
                "nombre": it.nombre,
                "cantidad": it.cantidad,
                "precio_total": it.precio_total,
                "categoria": it.categoria,
                "public_key": it.public_key or self.cfg.pagopar_public_key,
            })

        payload = {
            "token": token,
            "public_key": self.cfg.pagopar_public_key,
            "operation_type": "sale",
            "tipo_pedido": "VENTA-COMERCIO",
            "monto_total": monto_total,
            "id_pedido_comercio": order_id,
            "descripcion_resumen": description,
            "fecha_maxima_pago": fecha_maxima_pago or "2099-12-31 23:59:59",
            "comprador": {
                "ruc": buyer.ruc,
                "email": buyer.email,
                "nombre": buyer.nombre,
                "telefono": buyer.telefono,
                "direccion": buyer.direccion or "Asuncion, Paraguay",
                "documento": buyer.documento,
                "tipo_documento": buyer.tipo_documento.value,
                "razon_social": buyer.razon_social,
            },
            "compras_items": formatted_items,
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        last_error: Optional[Exception] = None
        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.cfg.request_timeout_seconds) as client:
                    logger.info(
                        "Calling Pagopar initiate_transaction url=%s order_id=%s attempt=%d/%d",
                        url,
                        order_id,
                        attempt,
                        self.cfg.max_retries,
                    )
                    resp = await client.post(url, json=payload, headers=headers)

                if resp.status_code >= 500:
                    logger.warning("Pagopar server error status=%d body=%s", resp.status_code, resp.text)
                    if attempt < self.cfg.max_retries:
                        await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                        continue
                    raise PagoparGatewayError(
                        f"Pagopar server error ({resp.status_code}): {resp.text}",
                        status_code=resp.status_code,
                    )

                if resp.status_code >= 400:
                    logger.error("Pagopar client rejection status=%d body=%s", resp.status_code, resp.text)
                    raise PagoparGatewayError(
                        f"Pagopar rejected order ({resp.status_code}): {resp.text}",
                        status_code=resp.status_code,
                    )

                data = resp.json()
                if not data.get("respuesta"):
                    error_msg = str(data.get("resultado", "Unknown gateway error"))
                    logger.error("Pagopar business error for order %s: %s", order_id, error_msg)
                    raise PagoparGatewayError(f"Pagopar error: {error_msg}", details=data)

                results = data.get("resultado", [])
                if not results or not isinstance(results, list):
                    raise PagoparGatewayError("Malformed Pagopar response: missing 'resultado' list", details=data)

                pagopar_hash = results[0].get("data")
                if not pagopar_hash:
                    raise PagoparGatewayError("Pagopar response did not return transaction hash 'data'", details=data)

                checkout_url = f"{self.cfg.resolved_checkout_base_url}/{pagopar_hash}"
                logger.info("Order %s registered successfully with hash %s", order_id, pagopar_hash)
                return {
                    "pagopar_hash": pagopar_hash,
                    "checkout_url": checkout_url,
                    "raw_response": data,
                }

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                logger.warning(
                    "Network error calling Pagopar (attempt %d/%d): %s",
                    attempt,
                    self.cfg.max_retries,
                    exc,
                )
                last_error = exc
                if attempt < self.cfg.max_retries:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
                raise PagoparNetworkTimeoutError(
                    f"Pagopar connection timed out or failed after {self.cfg.max_retries} attempts: {exc}"
                ) from exc

        if last_error:
            raise PagoparGatewayError(f"Pagopar request failed: {last_error}") from last_error
        raise PagoparGatewayError("Unexpected failure executing Pagopar request")

    async def poll_order_status(
        self,
        pagopar_hash: str,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Polls Pagopar API v1.1 POST /api/pedidos/1.1/traer to inspect transaction state.
        Serves as resilience fallback when webhook delivery is delayed or dropped.
        """
        url = f"{self.cfg.resolved_base_url}/api/pedidos/1.1/traer"
        token = self.compute_polling_token(self.cfg.pagopar_private_key)

        payload = {
            "token_publico": self.cfg.pagopar_public_key,
            "token": token,
            "hash_pedido": pagopar_hash,
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.cfg.request_timeout_seconds) as client:
                    logger.info("Polling Pagopar status for hash=%s (attempt %d/%d)", pagopar_hash, attempt, self.cfg.max_retries)
                    resp = await client.post(url, json=payload, headers=headers)

                if resp.status_code >= 500:
                    if attempt < self.cfg.max_retries:
                        await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                        continue
                    raise PagoparGatewayError(f"Pagopar server error during polling: {resp.status_code}", status_code=resp.status_code)

                if resp.status_code >= 400:
                    raise PagoparGatewayError(f"Pagopar polling rejected: {resp.status_code} {resp.text}", status_code=resp.status_code)

                data = resp.json()
                if not data.get("respuesta"):
                    error_msg = str(data.get("resultado", "Polling returned false response"))
                    raise PagoparGatewayError(f"Pagopar polling error: {error_msg}", details=data)

                results = data.get("resultado", [])
                item = results[0] if results and isinstance(results, list) else {}

                return {
                    "pagado": bool(item.get("pagado", False)),
                    "forma_pago": item.get("forma_pago"),
                    "monto": item.get("monto"),
                    "numero_pedido": item.get("numero_pedido"),
                    "fecha_pago": item.get("fecha_pago"),
                    "raw_response": data,
                }

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt < self.cfg.max_retries:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
                raise PagoparNetworkTimeoutError(f"Polling Pagopar timed out after {self.cfg.max_retries} attempts: {exc}") from exc

        raise PagoparGatewayError("Unexpected failure executing Pagopar status polling")
