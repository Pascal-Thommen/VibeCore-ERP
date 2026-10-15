"""Pydantic schemas and dataclasses for VibeCore Finance Core API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthStatus(BaseModel):
    """Liveness response returned by the Core API."""

    model_config = ConfigDict(extra="allow")

    status: str = Field(description="Liveness status string")


class AccountCreate(BaseModel):
    """Payload to create a chart-of-accounts entry."""

    model_config = ConfigDict(extra="allow")

    code: str
    name: str
    type: str
    description: str | None = None


class JournalEntryLineCreate(BaseModel):
    """Single balanced debit or credit line in a journal entry."""

    model_config = ConfigDict(extra="allow")

    account_id: str
    debit: float = 0.0
    credit: float = 0.0
    description: str | None = None


class JournalEntryCreate(BaseModel):
    """Double-entry journal header and lines payload."""

    model_config = ConfigDict(extra="allow")

    date: str
    description: str
    lines: list[JournalEntryLineCreate] = Field(default_factory=list)
    meta: dict[str, Any] | None = None
