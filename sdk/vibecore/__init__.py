"""Universal Python SDK for VibeCore and Modular Microservice Adapters."""

from vibecore.auth.client import AuthClient
from vibecore.client import CoreClient, HealthStatus, VibeCoreClient
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
from vibecore.payments.pagopar.client import PagoparClient
from vibecore.payments.stripe.client import StripeClient
from vibecore.storage.client import StorageClient

__all__ = [
    "VibeCoreClient",
    "CoreClient",
    "HealthStatus",
    "AuthClient",
    "StorageClient",
    "PagoparClient",
    "StripeClient",
    "VibeCoreError",
    "AuthenticationError",
    "StorageError",
    "StorageNotFoundError",
    "StorageValidationError",
    "StorageAuthenticationError",
    "PaymentError",
    "PaymentNotFoundError",
    "PaymentGatewayError",
    "PaymentTimeoutError",
    "NetworkError",
    "TimeoutError",
]
