"""
VibeCore ERP Auth Adapter - Structured Audit Logging & Observability (Säule 4).
Generates structured JSON logs with correlation trace IDs.
Never logs secrets, private keys, or raw tokens.
"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Context variable to hold the trace ID for the current async request
trace_id_ctx: ContextVar[str | None] = ContextVar("trace_id", default=None)


def get_current_trace_id() -> str:
    tid = trace_id_ctx.get()
    if not tid:
        tid = f"vc_tr_{uuid.uuid4().hex[:16]}"
        trace_id_ctx.set(tid)
    return tid


def set_current_trace_id(trace_id: str) -> None:
    trace_id_ctx.set(trace_id)


SENSITIVE_KEYS = {
    "password",
    "secret",
    "client_secret",
    "jwt_secret",
    "cookie_secret",
    "access_token",
    "id_token",
    "refresh_token",
    "code",
    "code_verifier",
    "authorization",
    "cookie",
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
                sanitize_dict(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized


class JsonAuditFormatter(logging.Formatter):
    """Formats log records as single-line JSON with trace_id and ISO-8601 timestamp."""

    def format(self, record: logging.LogRecord) -> str:
        tid = trace_id_ctx.get() or getattr(record, "trace_id", None) or "system"
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": tid,
        }
        if hasattr(record, "event_data") and isinstance(record.event_data, dict):
            payload["data"] = sanitize_dict(record.event_data)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


# Initialize logger
logger = logging.getLogger("vibecore.auth")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonAuditFormatter())
logger.handlers = [handler]
logger.propagate = False


def log_audit_event(
    event_name: str,
    message: str,
    level: int = logging.INFO,
    data: dict[str, Any] | None = None,
    exc_info: Exception | None = None,
) -> None:
    """Logs a structured audit event for authentication actions."""
    event_payload = {"event": event_name}
    if data:
        event_payload.update(data)
    extra = {"event_data": event_payload, "trace_id": get_current_trace_id()}
    logger.log(level, f"[{event_name}] {message}", extra=extra, exc_info=exc_info)
