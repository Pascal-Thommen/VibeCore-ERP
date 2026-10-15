"""Pytest configuration and test transport fixtures for VibeCore SDK."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest


def make_mock_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.MockTransport:
    """Helper to create an httpx.MockTransport wrapping a handler."""
    return httpx.MockTransport(handler)


@pytest.fixture
def mock_json_response() -> Callable[[int, Any], httpx.Response]:
    def _create(
        status_code: int, data: Any, headers: dict[str, str] | None = None
    ) -> httpx.Response:
        resp_headers = {"content-type": "application/json"}
        if headers:
            resp_headers.update(headers)
        return httpx.Response(
            status_code=status_code,
            headers=resp_headers,
            content=json.dumps(data).encode("utf-8"),
        )

    return _create
