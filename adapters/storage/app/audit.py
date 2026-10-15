"""
Structured JSON logging and observability (Säule 4) for VibeCore S3 Storage Adapter.
"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Context variable to hold correlation / trace ID across async requests
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_current_correlation_id() -> str:
    cid = correlation_id_ctx.get()
    if not cid:
        cid = f"vc_stor_{uuid.uuid4().hex[:16]}"
        correlation_id_ctx.set(cid)
    return cid


def set_current_correlation_id(correlation_id: str) -> None:
    correlation_id_ctx.set(correlation_id)


SENSITIVE_KEYS = {
    "password",
    "secret",
    "secret_key",
    "storage_secret_key",
    "access_key",
    "storage_access_key",
    "api_key",
    "storage_api_key",
    "authorization",
    "token",
}


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively redacts sensitive values from dictionaries before logging."""
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        if any(s in key.lower() for s in SENSITIVE_KEYS):
            if isinstance(value, str) and len(value) > 6:
                sanitized[key] = f"{value[:3]}***[REDACTED]"
            else:
                sanitized[key] = "***[REDACTED]"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_dict(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized


class JsonAuditFormatter(logging.Formatter):
    """Formats log records as single-line JSON with correlation_id and UTC timestamp."""

    def format(self, record: logging.LogRecord) -> str:
        cid = (
            correlation_id_ctx.get()
            or getattr(record, "correlation_id", None)
            or "system"
        )
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": cid,
        }
        if hasattr(record, "event_data") and isinstance(record.event_data, dict):
            payload["data"] = sanitize_dict(record.event_data)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


logger = logging.getLogger("vibecore.storage")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonAuditFormatter())
logger.handlers = [handler]
logger.propagate = False


def log_storage_event(
    event_name: str,
    message: str,
    level: int = logging.INFO,
    data: dict[str, Any] | None = None,
    exc_info: Exception | None = None,
) -> None:
    """Logs a structured event for storage operations."""
    event_payload = {"event": event_name}
    if data:
        event_payload.update(data)
    extra = {
        "event_data": event_payload,
        "correlation_id": get_current_correlation_id(),
    }
    logger.log(level, f"[{event_name}] {message}", extra=extra, exc_info=exc_info)
