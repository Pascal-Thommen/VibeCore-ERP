"""Unit tests for the unified VibeCoreClient."""

import pytest

from vibecore.auth.client import AuthClient
from vibecore.client import VibeCoreClient
from vibecore.core.client import CoreClient
from vibecore.payments.pagopar.client import PagoparClient
from vibecore.payments.stripe.client import StripeClient
from vibecore.storage.client import StorageClient


def test_vibecore_client_lazy_properties():
    client = VibeCoreClient(
        core_url="http://core.test",
        core_token="jwt-123",
        auth_url="http://auth.test",
        storage_url="http://storage.test",
        storage_api_key="storage-key",
        pagopar_url="http://pagopar.test",
        pagopar_api_key="pagopar-key",
        stripe_url="http://stripe.test",
        stripe_api_key="stripe-key",
    )

    assert isinstance(client.core, CoreClient)
    assert isinstance(client.auth, AuthClient)
    assert isinstance(client.storage, StorageClient)
    assert isinstance(client.pagopar, PagoparClient)
    assert isinstance(client.stripe, StripeClient)

    # Calling property again returns the same instance
    assert client.core is client.core
    assert client.auth is client.auth

    client.close()


def test_vibecore_client_missing_config_raises():
    empty_client = VibeCoreClient()

    with pytest.raises(ValueError, match="core_url"):
        _ = empty_client.core

    with pytest.raises(ValueError, match="auth_url"):
        _ = empty_client.auth

    with pytest.raises(ValueError, match="storage_url"):
        _ = empty_client.storage

    with pytest.raises(ValueError, match="pagopar_url"):
        _ = empty_client.pagopar

    with pytest.raises(ValueError, match="stripe_url"):
        _ = empty_client.stripe

    core_no_token = VibeCoreClient(core_url="http://core.test")
    with pytest.raises(ValueError, match="core_token"):
        _ = core_no_token.core


def test_vibecore_client_context_manager():
    with VibeCoreClient(
        core_url="http://core.test",
        core_token="token",
        auth_url="http://auth.test",
    ) as client:
        _ = client.core
        _ = client.auth

    # Verify clients are closed
    assert client.core._client.is_closed is True
    assert client.auth._client.is_closed is True
