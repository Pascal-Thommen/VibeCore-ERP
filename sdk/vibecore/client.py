"""Initial typed client boundary for the VibeCore Finance Core API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

import httpx


@dataclass(frozen=True, slots=True)
class HealthStatus:
    """Liveness response returned by the Core API."""

    status: str


class CoreClient:
    """Connect to an authenticated Core API; resource methods will be added here."""

    def __init__(self, base_url: str, *, access_token: str, timeout: float = 10.0) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
        )

    def health(self) -> HealthStatus:
        """Check the Core API liveness endpoint."""
        response = self._client.get("/health")
        response.raise_for_status()
        return HealthStatus(status=response.json()["status"])

    def create_account(self, data: dict) -> dict:
        """Create a chart-of-accounts entry."""
        response = self._client.post("/api/v1/accounts", json=data)
        response.raise_for_status()
        return response.json()

    def get_account(self, account_id: str) -> dict:
        """Retrieve an account by ID."""
        response = self._client.get(f"/api/v1/accounts/{account_id}")
        response.raise_for_status()
        return response.json()

    def list_accounts(self, offset: int = 0, limit: int = 100) -> list[dict]:
        """List chart-of-accounts entries."""
        response = self._client.get("/api/v1/accounts", params={"offset": offset, "limit": limit})
        response.raise_for_status()
        return response.json()

    def create_journal_entry(self, data: dict) -> dict:
        """Create a double-entry journal entry header and lines."""
        response = self._client.post("/api/v1/journal-entries", json=data)
        response.raise_for_status()
        return response.json()

    def get_journal_entry(self, journal_entry_id: str) -> dict:
        """Retrieve a journal entry by ID."""
        response = self._client.get(f"/api/v1/journal-entries/{journal_entry_id}")
        response.raise_for_status()
        return response.json()

    def list_journal_entries(self, offset: int = 0, limit: int = 100) -> list[dict]:
        """List journal entries."""
        response = self._client.get("/api/v1/journal-entries", params={"offset": offset, "limit": limit})
        response.raise_for_status()
        return response.json()

    def post_journal_entry(self, journal_entry_id: str, data: dict) -> dict:
        """Post and lock a balanced journal entry with human approval."""
        response = self._client.post(f"/api/v1/journal-entries/{journal_entry_id}/post", json=data)
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
