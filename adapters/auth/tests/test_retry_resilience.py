"""
Tests for Network Resilience, Timeout Handling, and Exponential Backoff Retries (Säule 1: Resilienz).
"""

from unittest.mock import AsyncMock, MagicMock
import httpx
import pytest

from app.config import Settings
from app.google_client import (
    GoogleAuthException,
    GoogleAuthTimeoutException,
    GoogleOAuthClient,
)


@pytest.mark.asyncio
async def test_retry_mechanism_recovers_after_transient_503():
    settings = Settings(
        http_max_retries=2,
        http_retry_delay_seconds=0.01,
        http_retry_backoff_factor=1.5,
    )
    client = GoogleOAuthClient(app_settings=settings)

    mock_resp_503 = MagicMock(spec=httpx.Response)
    mock_resp_503.status_code = 503

    mock_resp_200 = MagicMock(spec=httpx.Response)
    mock_resp_200.status_code = 200

    call_count = 0

    async def mock_request_fn(c):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return mock_resp_503
        return mock_resp_200

    resp = await client._execute_with_retry(mock_request_fn, "test_transient_recovery")
    assert resp.status_code == 200
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_mechanism_fails_when_all_retries_fail():
    settings = Settings(
        http_max_retries=2,
        http_retry_delay_seconds=0.01,
        http_retry_backoff_factor=1.5,
    )
    client = GoogleOAuthClient(app_settings=settings)

    mock_resp_502 = MagicMock(spec=httpx.Response)
    mock_resp_502.status_code = 502

    call_count = 0

    async def mock_request_fn(c):
        nonlocal call_count
        call_count += 1
        return mock_resp_502

    # Should return after exhausting retries
    resp = await client._execute_with_retry(mock_request_fn, "test_all_fail")
    assert resp.status_code == 502
    assert call_count == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_retry_mechanism_handles_network_exceptions():
    settings = Settings(
        http_max_retries=1,
        http_retry_delay_seconds=0.01,
    )
    client = GoogleOAuthClient(app_settings=settings)

    call_count = 0

    async def mock_request_fn(c):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("Connection refused by Google proxy")
        mock_resp_200 = MagicMock(spec=httpx.Response)
        mock_resp_200.status_code = 200
        return mock_resp_200

    resp = await client._execute_with_retry(mock_request_fn, "test_network_recovery")
    assert resp.status_code == 200
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_mechanism_timeout_exception():
    settings = Settings(
        http_max_retries=1,
        http_retry_delay_seconds=0.01,
    )
    client = GoogleOAuthClient(app_settings=settings)

    async def mock_timeout_fn(c):
        raise httpx.ReadTimeout("Timed out reading from Google")

    with pytest.raises(GoogleAuthTimeoutException, match="Timeout communicating"):
        await client._execute_with_retry(mock_timeout_fn, "test_timeout_fail")
