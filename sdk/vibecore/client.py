"""VibeCore Unified Client and Core Client exports."""

from __future__ import annotations

from typing import Self

import httpx

from vibecore.auth.client import AuthClient
from vibecore.core.client import CoreClient
from vibecore.core.models import HealthStatus
from vibecore.payments.pagopar.client import PagoparClient
from vibecore.payments.stripe.client import StripeClient
from vibecore.storage.client import StorageClient


class VibeCoreClient:
    """
    Unified entrypoint client for the VibeCore ecosystem.

    Provides convenient, lazy-loaded access to Finance Core, Google Auth,
    S3 Storage, Pagopar, and Stripe payment adapters.
    """

    def __init__(
        self,
        *,
        core_url: str | None = None,
        core_token: str | None = None,
        auth_url: str | None = None,
        storage_url: str | None = None,
        storage_api_key: str | None = None,
        pagopar_url: str | None = None,
        pagopar_api_key: str | None = None,
        stripe_url: str | None = None,
        stripe_api_key: str | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._core_url = core_url
        self._core_token = core_token
        self._auth_url = auth_url
        self._storage_url = storage_url
        self._storage_api_key = storage_api_key
        self._pagopar_url = pagopar_url
        self._pagopar_api_key = pagopar_api_key
        self._stripe_url = stripe_url
        self._stripe_api_key = stripe_api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self._transport = transport

        self._core: CoreClient | None = None
        self._auth: AuthClient | None = None
        self._storage: StorageClient | None = None
        self._pagopar: PagoparClient | None = None
        self._stripe: StripeClient | None = None

    @property
    def core(self) -> CoreClient:
        """Access the CoreClient instance."""
        if self._core is None:
            if not self._core_url:
                raise ValueError("core_url must be provided to access CoreClient.")
            if not self._core_token:
                raise ValueError("core_token must be provided to access CoreClient.")
            self._core = CoreClient(
                self._core_url,
                access_token=self._core_token,
                timeout=self._timeout,
                max_retries=self._max_retries,
                transport=self._transport,
            )
        return self._core

    @property
    def auth(self) -> AuthClient:
        """Access the AuthClient instance."""
        if self._auth is None:
            if not self._auth_url:
                raise ValueError("auth_url must be provided to access AuthClient.")
            self._auth = AuthClient(
                self._auth_url,
                timeout=self._timeout,
                max_retries=self._max_retries,
                transport=self._transport,
            )
        return self._auth

    @property
    def storage(self) -> StorageClient:
        """Access the StorageClient instance."""
        if self._storage is None:
            if not self._storage_url:
                raise ValueError("storage_url must be provided to access StorageClient.")
            self._storage = StorageClient(
                self._storage_url,
                api_key=self._storage_api_key,
                timeout=self._timeout,
                max_retries=self._max_retries,
                transport=self._transport,
            )
        return self._storage

    @property
    def pagopar(self) -> PagoparClient:
        """Access the PagoparClient instance."""
        if self._pagopar is None:
            if not self._pagopar_url:
                raise ValueError("pagopar_url must be provided to access PagoparClient.")
            self._pagopar = PagoparClient(
                self._pagopar_url,
                api_key=self._pagopar_api_key,
                timeout=self._timeout,
                max_retries=self._max_retries,
                transport=self._transport,
            )
        return self._pagopar

    @property
    def stripe(self) -> StripeClient:
        """Access the StripeClient instance."""
        if self._stripe is None:
            if not self._stripe_url:
                raise ValueError("stripe_url must be provided to access StripeClient.")
            self._stripe = StripeClient(
                self._stripe_url,
                api_key=self._stripe_api_key,
                timeout=self._timeout,
                max_retries=self._max_retries,
                transport=self._transport,
            )
        return self._stripe

    def close(self) -> None:
        """Close all initialized adapter clients."""
        for client in (
            self._core,
            self._auth,
            self._storage,
            self._pagopar,
            self._stripe,
        ):
            if client is not None:
                client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = ["CoreClient", "HealthStatus", "VibeCoreClient"]
