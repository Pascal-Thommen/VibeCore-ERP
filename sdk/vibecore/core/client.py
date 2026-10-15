"""Typed client boundary for the VibeCore Finance Core API."""

from __future__ import annotations

from typing import Any

import httpx

from vibecore._base import BaseHttpClient
from vibecore.core.models import HealthStatus


class CoreClient(BaseHttpClient):
    """Connect to an authenticated Core API; resource methods will be added here."""

    def __init__(
        self,
        base_url: str,
        *,
        access_token: str,
        timeout: float = 10.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
            max_retries=max_retries,
            transport=transport,
        )

    def health(self) -> HealthStatus:
        """Check the Core API liveness endpoint."""
        resp = self._request("GET", "/health")
        self._raise_for_status(resp, adapter_type="core")
        return HealthStatus.model_validate(resp.json())

    def create_account(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a chart-of-accounts entry."""
        resp = self._request("POST", "/api/v1/accounts", json=data)
        self._raise_for_status(resp, adapter_type="core")
        return resp.json()

    def get_account(self, account_id: str) -> dict[str, Any]:
        """Retrieve an account by ID."""
        resp = self._request("GET", f"/api/v1/accounts/{account_id}")
        self._raise_for_status(resp, adapter_type="core")
        return resp.json()

    def list_accounts(self, offset: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        """List chart-of-accounts entries."""
        resp = self._request("GET", "/api/v1/accounts", params={"offset": offset, "limit": limit})
        self._raise_for_status(resp, adapter_type="core")
        return resp.json()

    def create_journal_entry(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a double-entry journal entry header and lines."""
        resp = self._request("POST", "/api/v1/journal-entries", json=data)
        self._raise_for_status(resp, adapter_type="core")
        return resp.json()

    def get_journal_entry(self, journal_entry_id: str) -> dict[str, Any]:
        """Retrieve a journal entry by ID."""
        resp = self._request("GET", f"/api/v1/journal-entries/{journal_entry_id}")
        self._raise_for_status(resp, adapter_type="core")
        return resp.json()

    def list_journal_entries(self, offset: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        """List journal entries."""
        resp = self._request(
            "GET", "/api/v1/journal-entries", params={"offset": offset, "limit": limit}
        )
        self._raise_for_status(resp, adapter_type="core")
        return resp.json()

    def post_journal_entry(self, journal_entry_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Post and lock a balanced journal entry with human approval."""
        resp = self._request("POST", f"/api/v1/journal-entries/{journal_entry_id}/post", json=data)
        self._raise_for_status(resp, adapter_type="core")
        return resp.json()
