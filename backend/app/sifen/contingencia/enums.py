"""
SIFEN Contingencia Enums and Status Definitions.
"""

from enum import StrEnum

from ..constants import (
    CONTINGENCIA_CRITICAL_HOURS,
    CONTINGENCIA_MAX_HOURS,
    CONTINGENCIA_WARNING_HOURS,
    EMISSION_CONTINGENCIA,
    EMISSION_NORMAL,
    EMISSION_TYPE_DESCRIPTIONS,
    OutboxStatus,
)


class CircuitState(StrEnum):
    """Circuit breaker states for SIFEN transmission failover."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class AlertSeverity(StrEnum):
    """Severity levels for 72h deadline monitoring."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EXPIRED = "EXPIRED"


__all__ = [
    "AlertSeverity",
    "CircuitState",
    "CONTINGENCIA_CRITICAL_HOURS",
    "CONTINGENCIA_MAX_HOURS",
    "CONTINGENCIA_WARNING_HOURS",
    "EMISSION_CONTINGENCIA",
    "EMISSION_NORMAL",
    "EMISSION_TYPE_DESCRIPTIONS",
    "OutboxStatus",
]
