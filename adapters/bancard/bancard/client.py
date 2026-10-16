"""HTTP client for communicating with the external Bancard vPOS 2.0 API gateway."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union
import httpx

from bancard.config import settings
from bancard.constants import (
    ENDPOINT_CARDS_NEW,
    ENDPOINT_CHARGE,
    ENDPOINT_ROLLBACK,
    ENDPOINT_SINGLE_BUY,
)
from bancard.crypto import (
    format_bancard_amount,
    generate_card_new_token,
    generate_charge_token,
    generate_rollback_token,
    generate_single_buy_token,
)

logger = logging.getLogger("bancard.client")


class BancardGatewayError(Exception):
    """Raised when the Bancard vPOS gateway rejects an operation or returns an error."""

    def __init__(self, message: str, response_data: Optional[Dict[str, Any]] = None, status_code: int = 502) -> None:
        super().__init__(message)
        self.response_data = response_data or {}
        self.status_code = status_code


class BancardGatewayClient:
    """Enterprise client for Bancard vPOS 2.0 with timeout boundaries and strict hashing."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        public_key: Optional[str] = None,
        private_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.base_url = (base_url or settings.bancard_base_url).rstrip("/")
        self.public_key = public_key or settings.bancard_public_key
        self.private_key = private_key or settings.bancard_private_key
        self.timeout = timeout if timeout is not None else settings.request_timeout_seconds

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        logger.info("Calling Bancard gateway", extra={"url": url, "endpoint": endpoint})
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload, headers={"Content-Type": "application/json"})
                if resp.status_code >= 400:
                    raise BancardGatewayError(
                        f"Bancard returned HTTP {resp.status_code}: {resp.text}",
                        response_data={"status_code": resp.status_code, "body": resp.text},
                        status_code=resp.status_code,
                    )
                data = resp.json()
                if data.get("status") == "error":
                    msgs = data.get("messages", [])
                    raise BancardGatewayError(
                        f"Bancard operation error: {msgs}",
                        response_data=data,
                        status_code=400,
                    )
                return data
        except httpx.TimeoutException as exc:
            logger.error("Bancard request timed out", extra={"endpoint": endpoint, "timeout": self.timeout})
            raise BancardGatewayError(f"Bancard gateway timed out after {self.timeout}s: {str(exc)}", status_code=504)
        except httpx.NetworkError as exc:
            logger.error("Bancard network error", extra={"endpoint": endpoint, "error": str(exc)})
            raise BancardGatewayError(f"Bancard network connectivity failure: {str(exc)}", status_code=502)

    def single_buy(
        self,
        shop_process_id: Union[int, str],
        amount: Union[float, int, str],
        currency: str,
        description: str,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Request a Bancard single_buy process token for checkout iframe/redirect."""
        amount_str = format_bancard_amount(amount)
        token = generate_single_buy_token(self.private_key, shop_process_id, amount_str, currency)

        payload = {
            "public_key": self.public_key,
            "operation": {
                "token": token,
                "shop_process_id": int(shop_process_id),
                "amount": amount_str,
                "currency": currency,
                "description": description,
                "return_url": return_url or "https://vibecore.local/payment/return",
                "cancel_url": cancel_url or "https://vibecore.local/payment/cancel",
            },
        }

        return self._post(ENDPOINT_SINGLE_BUY, payload)

    def cards_new(
        self,
        card_id: Union[int, str],
        user_id: Union[int, str],
        user_cell_phone: Optional[str] = None,
        user_mail: Optional[str] = None,
        return_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Request a process_id to display the card registration catastro iframe."""
        token = generate_card_new_token(self.private_key, card_id, user_id)

        payload = {
            "public_key": self.public_key,
            "operation": {
                "token": token,
                "card_id": int(card_id),
                "user_id": str(user_id),
                "user_cell_phone": user_cell_phone or "",
                "user_mail": user_mail or "",
                "return_url": return_url or "https://vibecore.local/cards/return",
            },
        }

        return self._post(ENDPOINT_CARDS_NEW, payload)

    def charge(
        self,
        shop_process_id: Union[int, str],
        amount: Union[float, int, str],
        currency: str,
        alias_token: str,
        description: str,
    ) -> Dict[str, Any]:
        """Execute a direct 1-click or recurring charge using a registered card alias token."""
        amount_str = format_bancard_amount(amount)
        token = generate_charge_token(self.private_key, shop_process_id, amount_str, currency, alias_token)

        payload = {
            "public_key": self.public_key,
            "operation": {
                "token": token,
                "shop_process_id": int(shop_process_id),
                "amount": amount_str,
                "currency": currency,
                "alias_token": alias_token,
                "description": description,
            },
        }

        return self._post(ENDPOINT_CHARGE, payload)

    def rollback(
        self,
        shop_process_id: Union[int, str],
    ) -> Dict[str, Any]:
        """Execute rollback / cancellation of a transaction on Bancard."""
        token = generate_rollback_token(self.private_key, shop_process_id)

        payload = {
            "public_key": self.public_key,
            "operation": {
                "token": token,
                "shop_process_id": int(shop_process_id),
            },
        }

        return self._post(ENDPOINT_ROLLBACK, payload)
