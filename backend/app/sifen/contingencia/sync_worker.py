"""
Background Synchronization Worker with Exponential Backoff and Batch Transmission.
Transmits offline contingencia documents to DNIT SIFEN when network connectivity is restored.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable

from .circuit_breaker import CircuitBreaker
from .enums import OutboxStatus
from .models import BatchSyncResult, ContingenciaRecord, DeadlineAlert
from .outbox_queue import DurableOutboxQueue

logger = logging.getLogger(__name__)


class TransmissionError(Exception):
    """Temporary / recoverable transmission failure (e.g. timeout, connection lost)."""
    pass


class BusinessRejectionError(Exception):
    """Permanent rejection by DNIT / SIFEN portal (e.g. schema invalid, duplicate CDC)."""
    pass


class ContingenciaSyncWorker:
    """
    Worker coordinating the background transmission of offline contingencia DTEs.
    Applies exponential backoff, circuit-breaker awareness, and 72h deadline enforcement.
    """

    def __init__(
        self,
        queue: DurableOutboxQueue,
        transmitter: Callable[[ContingenciaRecord], dict[str, Any]] | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        base_backoff_seconds: float = 2.0,
        backoff_factor: float = 2.0,
        max_backoff_seconds: float = 300.0,
        alert_callback: Callable[[DeadlineAlert], None] | None = None,
    ) -> None:
        self.queue = queue
        self.transmitter = transmitter or self._mock_transmitter
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.base_backoff = base_backoff_seconds
        self.backoff_factor = backoff_factor
        self.max_backoff = max_backoff_seconds
        self.alert_callback = alert_callback

    def _mock_transmitter(self, record: ContingenciaRecord) -> dict[str, Any]:
        """Default successful mock transmitter for local and staging environments."""
        return {
            "protocol": f"SIFEN-DNIT-{record.cdc[:8]}-{int(datetime.now().timestamp())}",
            "status": "ACCEPTED",
            "message": "Aprobado por DNIT SIFEN",
        }

    def process_pending_batch(
        self,
        batch_size: int = 50,
        reference_time: datetime | None = None,
    ) -> BatchSyncResult:
        """
        Process a batch of eligible offline contingencia documents:
        1. Check deadlines and trigger alerts (marking >72h as EXPIRED).
        2. Verify if circuit breaker permits online attempts.
        3. Transmit each pending document, applying exponential backoff on network failures.
        """
        ref_time = reference_time or datetime.now()
        result = BatchSyncResult()

        # Step 1: Deadline audit and expiration enforcement
        alerts = self.queue.check_deadlines(reference_time=ref_time)
        for alert in alerts:
            if alert.severity.value == "EXPIRED":
                result.expired_count += 1
            if self.alert_callback:
                self.alert_callback(alert)

        # Step 2: Circuit breaker check
        if not self.circuit_breaker.can_attempt():
            logger.info("Circuit breaker is OPEN. Skipping batch transmission until recovery.")
            return result

        # Step 3: Fetch pending batch
        pending_records = self.queue.get_pending_batch(limit=batch_size, reference_time=ref_time)
        result.total_scanned = len(pending_records)

        for record in pending_records:
            # Check individual 72h expiration
            if record.is_expired:
                self.queue.update_status(
                    doc_id=record.id,
                    new_status=OutboxStatus.EXPIRED,
                    error="Exceeded 72h contingencia transmission window",
                )
                result.expired_count += 1
                continue

            # Mark TRANSMITTING
            self.queue.update_status(
                doc_id=record.id,
                new_status=OutboxStatus.TRANSMITTING,
                detail="Batch transmitter attempting delivery to DNIT SIFEN",
            )

            try:
                transmit_res = self.transmitter(record)
                protocol = transmit_res.get("protocol", "DNIT-OK")

                # Successful delivery
                self.circuit_breaker.record_success()
                self.queue.update_status(
                    doc_id=record.id,
                    new_status=OutboxStatus.ACCEPTED,
                    dnit_protocol=protocol,
                    transmitted_at=datetime.now(),
                    detail=f"Accepted by DNIT, protocol: {protocol}",
                )
                result.accepted_count += 1

            except BusinessRejectionError as bre:
                # Fatal rejection by tax authority (e.g. invalid tax ID or duplicate)
                self.queue.update_status(
                    doc_id=record.id,
                    new_status=OutboxStatus.REJECTED,
                    error=str(bre),
                    detail="Rejected by DNIT SIFEN validation rules",
                )
                result.rejected_count += 1
                result.errors.append({"document_id": record.id, "cdc": record.cdc, "error": str(bre)})

            except Exception as exc:
                # Transient network timeout or connection failure
                self.circuit_breaker.record_failure(exc)

                # Exponential backoff calculation
                delay_sec = min(
                    self.max_backoff,
                    self.base_backoff * (self.backoff_factor ** record.retry_count),
                )
                next_retry = datetime.now() + timedelta(seconds=delay_sec)

                self.queue.update_status(
                    doc_id=record.id,
                    new_status=OutboxStatus.QUEUED_OFFLINE,
                    error=str(exc),
                    next_retry_at=next_retry,
                    increment_retry=True,
                    detail=f"Network failure, scheduled retry #{record.retry_count + 1} at {next_retry.isoformat()}",
                )
                result.retry_count += 1
                result.errors.append({"document_id": record.id, "cdc": record.cdc, "error": str(exc)})

                # If circuit breaker tripped open due to this failure, stop batch
                if not self.circuit_breaker.can_attempt():
                    logger.warning("Circuit breaker tripped to OPEN during batch. Aborting remaining batch.")
                    break

        return result
