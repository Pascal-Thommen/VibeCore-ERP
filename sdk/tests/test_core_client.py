"""Unit tests for CoreClient (Finance Core Accounting API)."""

import json

import httpx
import pytest

from vibecore.core.client import CoreClient
from vibecore.core.models import HealthStatus
from vibecore.exceptions import AuthenticationError


def test_core_client_health():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        assert request.headers.get("authorization") == "Bearer token-123"
        return httpx.Response(200, json={"status": "ok"})

    with CoreClient(
        "http://core.test", access_token="token-123", transport=httpx.MockTransport(handler)
    ) as client:
        health = client.health()
        assert isinstance(health, HealthStatus)
        assert health.status == "ok"


def test_core_client_accounts_crud():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v1/accounts":
            body = json.loads(request.content.decode("utf-8"))
            return httpx.Response(201, json={"id": "acc-1", **body})
        if request.method == "GET" and request.url.path == "/api/v1/accounts/acc-1":
            return httpx.Response(200, json={"id": "acc-1", "code": "1001", "name": "Cash"})
        if request.method == "GET" and request.url.path == "/api/v1/accounts":
            return httpx.Response(200, json=[{"id": "acc-1", "code": "1001", "name": "Cash"}])
        return httpx.Response(404)

    with CoreClient(
        "http://core.test", access_token="token-123", transport=httpx.MockTransport(handler)
    ) as client:
        created = client.create_account({"code": "1001", "name": "Cash", "type": "asset"})
        assert created["id"] == "acc-1"

        fetched = client.get_account("acc-1")
        assert fetched["code"] == "1001"

        listed = client.list_accounts(offset=0, limit=10)
        assert len(listed) == 1
        assert listed[0]["id"] == "acc-1"


def test_core_client_journal_entries():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v1/journal-entries":
            return httpx.Response(201, json={"id": "je-1", "status": "draft"})
        if request.method == "GET" and request.url.path == "/api/v1/journal-entries/je-1":
            return httpx.Response(200, json={"id": "je-1", "status": "draft"})
        if request.method == "GET" and request.url.path == "/api/v1/journal-entries":
            return httpx.Response(200, json=[{"id": "je-1", "status": "draft"}])
        if request.method == "POST" and request.url.path == "/api/v1/journal-entries/je-1/post":
            return httpx.Response(200, json={"id": "je-1", "status": "posted"})
        return httpx.Response(404)

    with CoreClient(
        "http://core.test", access_token="token-123", transport=httpx.MockTransport(handler)
    ) as client:
        entry = client.create_journal_entry({"date": "2026-10-15", "description": "Test Entry"})
        assert entry["id"] == "je-1"

        get_res = client.get_journal_entry("je-1")
        assert get_res["status"] == "draft"

        list_res = client.list_journal_entries()
        assert len(list_res) == 1

        posted = client.post_journal_entry("je-1", {"approved_by": "Pascal"})
        assert posted["status"] == "posted"


def test_core_client_unauthorized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid token"})

    with CoreClient(
        "http://core.test", access_token="bad-token", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(AuthenticationError) as exc_info:
            client.health()
        assert exc_info.value.status_code == 401
