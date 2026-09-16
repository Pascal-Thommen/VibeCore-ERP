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

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
