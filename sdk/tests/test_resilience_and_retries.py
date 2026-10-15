"""Resilience, network failure, and retry tests for VibeCore SDK clients."""

import httpx
import pytest

from vibecore.auth.client import AuthClient
from vibecore.exceptions import NetworkError, StorageError, TimeoutError
from vibecore.storage.client import StorageClient


def test_retry_on_transient_503_success():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"detail": "Service temporarily unavailable"})
        return httpx.Response(200, json={"status": "ok", "version": "0.1.0"})

    client = StorageClient(
        "http://storage.test",
        max_retries=3,
        transport=httpx.MockTransport(handler),
    )
    client.retry_backoff_factor = 0.001  # fast tests

    res = client.health()
    assert res.status == "ok"
    assert attempts == 3
    client.close()


def test_retry_exhausted_raises_storage_error():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"detail": "Service persistently down"})

    client = StorageClient(
        "http://storage.test",
        max_retries=2,
        transport=httpx.MockTransport(handler),
    )
    client.retry_backoff_factor = 0.001

    with pytest.raises(StorageError) as exc_info:
        client.health()
    assert exc_info.value.status_code == 503
    assert attempts == 3  # 1 initial + 2 retries
    client.close()


def test_retry_on_connection_error():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise httpx.ConnectError("Network route unreachable")
        return httpx.Response(200, json={"status": "healthy", "service": "auth"})

    client = AuthClient(
        "http://auth.test",
        max_retries=2,
        transport=httpx.MockTransport(handler),
    )
    client.retry_backoff_factor = 0.001

    res = client.health()
    assert res.status == "healthy"
    assert attempts == 2
    client.close()


def test_connection_error_exhausted_raises_network_error():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("Connection refused by host")

    client = AuthClient(
        "http://auth.test",
        max_retries=1,
        transport=httpx.MockTransport(handler),
    )
    client.retry_backoff_factor = 0.001

    with pytest.raises(NetworkError) as exc_info:
        client.health()
    assert "Connection failed" in str(exc_info.value)
    assert attempts == 2
    client.close()


def test_client_timeout_raises_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Server took longer than 0.5s to respond")

    client = AuthClient(
        "http://auth.test",
        timeout=0.5,
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(TimeoutError) as exc_info:
        client.health()
    assert "timed out" in str(exc_info.value).lower()
    client.close()
