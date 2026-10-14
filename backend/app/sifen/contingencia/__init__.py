"""
SIFEN Offline-Contingencia & Durable Outbox Queue Module.
"""

from .circuit_breaker import CircuitBreaker, SifenCircuitBreakerOpenError
from .engine import SifenContingenciaEngine
from .enums import (
    AlertSeverity,
    CircuitState,
    CONTINGENCIA_CRITICAL_HOURS,
    CONTINGENCIA_MAX_HOURS,
    CONTINGENCIA_WARNING_HOURS,
    EMISSION_CONTINGENCIA,
    EMISSION_NORMAL,
    EMISSION_TYPE_DESCRIPTIONS,
    OutboxStatus,
)
from .kude_generator import KuDeGenerator, format_cdc_blocks
from .models import (
    BatchSyncResult,
    ContingenciaIssueResult,
    ContingenciaRecord,
    DeadlineAlert,
    KuDeReceipt,
)
from .outbox_queue import DurableOutboxQueue
from .sync_worker import (
    BusinessRejectionError,
    ContingenciaSyncWorker,
    TransmissionError,
)

__all__ = [
    "AlertSeverity",
    "BatchSyncResult",
    "BusinessRejectionError",
    "CONTINGENCIA_CRITICAL_HOURS",
    "CONTINGENCIA_MAX_HOURS",
    "CONTINGENCIA_WARNING_HOURS",
    "CircuitBreaker",
    "CircuitState",
    "ContingenciaIssueResult",
    "ContingenciaRecord",
    "ContingenciaSyncWorker",
    "DeadlineAlert",
    "DurableOutboxQueue",
    "EMISSION_CONTINGENCIA",
    "EMISSION_NORMAL",
    "EMISSION_TYPE_DESCRIPTIONS",
    "KuDeGenerator",
    "KuDeReceipt",
    "OutboxStatus",
    "SifenCircuitBreakerOpenError",
    "SifenContingenciaEngine",
    "TransmissionError",
    "format_cdc_blocks",
]
