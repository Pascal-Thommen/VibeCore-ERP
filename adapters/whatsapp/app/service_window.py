"""Tracking and enforcement of the Meta 24-hour customer service window."""

from __future__ import annotations

import re
import threading
from datetime import UTC, datetime, timedelta

from app.schemas import ServiceWindowStatus

WINDOW_DURATION_SECONDS = 86400  # 24 hours


def normalize_phone_number(raw_phone: str) -> str:
    """Normalize phone numbers to digits only, stripping +, whitespace, and dashes."""
    return re.sub(r"[^\d]", "", raw_phone)


class ServiceWindowManager:
    """Thread-safe in-memory tracker for WhatsApp 24-hour customer service windows."""

    def __init__(self, window_seconds: int = WINDOW_DURATION_SECONDS) -> None:
        self.window_seconds = window_seconds
        self._windows: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def record_incoming_message(
        self, phone_number: str, timestamp: datetime | None = None
    ) -> datetime:
        """Record an incoming customer interaction opening or refreshing the 24h window."""
        normalized = normalize_phone_number(phone_number)
        interaction_time = timestamp or datetime.now(UTC)
        if interaction_time.tzinfo is None:
            interaction_time = interaction_time.replace(tzinfo=UTC)

        with self._lock:
            existing = self._windows.get(normalized)
            if existing is None or interaction_time > existing:
                self._windows[normalized] = interaction_time
        return interaction_time

    def is_window_active(self, phone_number: str, current_time: datetime | None = None) -> bool:
        """Check if a phone number currently has an active 24-hour session window."""
        normalized = normalize_phone_number(phone_number)
        now = current_time or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        with self._lock:
            last_seen = self._windows.get(normalized)

        if last_seen is None:
            return False

        elapsed = (now - last_seen).total_seconds()
        return 0 <= elapsed <= self.window_seconds

    def get_window_status(
        self, phone_number: str, current_time: datetime | None = None
    ) -> ServiceWindowStatus:
        """Return structured status of the 24h customer service window."""
        normalized = normalize_phone_number(phone_number)
        now = current_time or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        with self._lock:
            last_seen = self._windows.get(normalized)

        if last_seen is None:
            return ServiceWindowStatus(
                phone_number=normalized,
                is_active=False,
                last_incoming_at=None,
                expires_at=None,
                remaining_seconds=0,
            )

        expires_at = last_seen + timedelta(seconds=self.window_seconds)
        remaining = int((expires_at - now).total_seconds())
        is_active = remaining > 0

        return ServiceWindowStatus(
            phone_number=normalized,
            is_active=is_active,
            last_incoming_at=last_seen,
            expires_at=expires_at,
            remaining_seconds=max(0, remaining),
        )

    def clear(self, phone_number: str | None = None) -> None:
        """Clear recorded windows (for testing or reset)."""
        with self._lock:
            if phone_number is not None:
                self._windows.pop(normalize_phone_number(phone_number), None)
            else:
                self._windows.clear()


service_window_manager = ServiceWindowManager()
