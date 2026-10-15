"""Uniform exception hierarchy for the VibeCore Python SDK."""

from __future__ import annotations

from typing import Any

import httpx


class VibeCoreError(Exception):
    """Base exception for all errors raised by the VibeCore SDK."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: Any | None = None,
        response: httpx.Response | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail
        self.response = response

    def __str__(self) -> str:
        if self.status_code:
            return f"[{self.status_code}] {self.message}"
        return self.message


class AuthenticationError(VibeCoreError):
    """Raised when authentication or authorization fails (401, 403, CSRF or token errors)."""

    pass


class StorageError(VibeCoreError):
    """Base exception for Storage adapter errors."""

    pass


class StorageNotFoundError(StorageError):
    """Raised when the requested file or object is not found (404)."""

    pass


class StorageValidationError(StorageError):
    """Raised when storage payload or parameters fail validation (400)."""

    pass


class StorageAuthenticationError(StorageError, AuthenticationError):
    """Raised when storage API key authentication fails (401, 403)."""

    pass


class PaymentError(VibeCoreError):
    """Base exception for Payment adapter errors (Pagopar, Stripe)."""

    pass


class PaymentNotFoundError(PaymentError):
    """Raised when an order or payment is not found (404)."""

    pass


class PaymentGatewayError(PaymentError):
    """Raised when an upstream payment gateway returns an error (502)."""

    pass


class PaymentTimeoutError(PaymentError):
    """Raised when an upstream payment gateway times out (504)."""

    pass


class NetworkError(VibeCoreError):
    """Raised when network connectivity fails."""

    pass


class TimeoutError(VibeCoreError):
    """Raised when an HTTP operation exceeds the configured timeout."""

    pass
