"""Base HTTP client with resilience, retries, and error handling for VibeCore SDK."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any, Self

import httpx

from vibecore.exceptions import (
    AuthenticationError,
    NetworkError,
    PaymentError,
    PaymentGatewayError,
    PaymentNotFoundError,
    PaymentTimeoutError,
    StorageAuthenticationError,
    StorageError,
    StorageNotFoundError,
    StorageValidationError,
    TimeoutError,
    VibeCoreError,
)

logger = logging.getLogger("vibecore.sdk")

RETRYABLE_STATUS_CODES = {502, 503, 504}


class BaseHttpClient:
    """Internal base class providing resilient HTTP transport and connection management."""

    def __init__(
        self,
        base_url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        retry_backoff_factor: float = 0.2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff_factor = retry_backoff_factor

        default_headers = {
            "User-Agent": "VibeCore-Python-SDK/0.1.0",
            "Accept": "application/json",
        }
        if headers:
            default_headers.update(headers)

        self._client = httpx.Client(
            base_url=self.base_url,
            headers=default_headers,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        """Release underlying HTTP connections."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Any = None,
        files: Any = None,
        headers: Mapping[str, str] | None = None,
        retry_on_status: set[int] | None = None,
    ) -> httpx.Response:
        """Execute HTTP request with configurable retries and exponential backoff."""
        retry_codes = retry_on_status or RETRYABLE_STATUS_CODES
        method_upper = method.upper()
        # By default, retry GET/HEAD/OPTIONS/DELETE/PUT safely
        is_idempotent = method_upper in {"GET", "HEAD", "OPTIONS", "DELETE", "PUT"}

        last_exception: Exception | None = None
        attempts = self.max_retries + 1

        for attempt in range(1, attempts + 1):
            try:
                response = self._client.request(
                    method=method_upper,
                    url=path,
                    params=params,
                    json=json,
                    data=data,
                    files=files,
                    headers=headers,
                )

                if response.status_code in retry_codes and (is_idempotent or attempt == 1):
                    if attempt < attempts:
                        backoff = self.retry_backoff_factor * (2 ** (attempt - 1))
                        time.sleep(backoff)
                        continue

                return response

            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_exception = exc
                if attempt < attempts:
                    backoff = self.retry_backoff_factor * (2 ** (attempt - 1))
                    time.sleep(backoff)
                    continue
                raise NetworkError(f"Connection failed to {self.base_url}{path}: {exc}") from exc
            except httpx.TimeoutException as exc:
                last_exception = exc
                if is_idempotent and attempt < attempts:
                    backoff = self.retry_backoff_factor * (2 ** (attempt - 1))
                    time.sleep(backoff)
                    continue
                raise TimeoutError(
                    f"Request timed out after {self.timeout}s on {method_upper} {path}: {exc}"
                ) from exc
            except httpx.RequestError as exc:
                raise NetworkError(f"HTTP request error: {exc}") from exc

        if last_exception:
            raise NetworkError(
                f"Request failed after {attempts} attempts: {last_exception}"
            ) from last_exception

        raise NetworkError("Unexpected request failure without response.")

    def _parse_error_payload(self, response: httpx.Response) -> tuple[str, Any]:
        """Extract user-friendly message and detail from response body."""
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = body.get("detail")
                message = body.get("message") or body.get("error")
                if message and detail:
                    return f"{message}: {detail}", body
                if detail:
                    return str(detail), body
                if message:
                    return str(message), body
                return response.text, body
        except Exception:
            pass
        return response.text or f"HTTP status {response.status_code}", None

    def _raise_for_status(
        self,
        response: httpx.Response,
        adapter_type: str = "core",
    ) -> None:
        """Map HTTP error status codes to typed VibeCore exceptions."""
        if response.is_success:
            return

        msg, body = self._parse_error_payload(response)
        code = response.status_code

        if adapter_type == "auth":
            if code in (401, 403):
                raise AuthenticationError(msg, status_code=code, detail=body, response=response)
            if code == 504:
                raise TimeoutError(msg, status_code=code, detail=body, response=response)
            raise VibeCoreError(msg, status_code=code, detail=body, response=response)

        if adapter_type == "storage":
            if code in (401, 403):
                raise StorageAuthenticationError(
                    msg, status_code=code, detail=body, response=response
                )
            if code == 404:
                raise StorageNotFoundError(msg, status_code=code, detail=body, response=response)
            if code == 400:
                raise StorageValidationError(msg, status_code=code, detail=body, response=response)
            raise StorageError(msg, status_code=code, detail=body, response=response)

        if adapter_type in ("pagopar", "stripe", "payment"):
            if code in (401, 403):
                raise AuthenticationError(msg, status_code=code, detail=body, response=response)
            if code == 404:
                raise PaymentNotFoundError(msg, status_code=code, detail=body, response=response)
            if code == 502:
                raise PaymentGatewayError(msg, status_code=code, detail=body, response=response)
            if code == 504:
                raise PaymentTimeoutError(msg, status_code=code, detail=body, response=response)
            raise PaymentError(msg, status_code=code, detail=body, response=response)

        # Default fallback
        if code in (401, 403):
            raise AuthenticationError(msg, status_code=code, detail=body, response=response)
        if code == 504:
            raise TimeoutError(msg, status_code=code, detail=body, response=response)
        raise VibeCoreError(msg, status_code=code, detail=body, response=response)
