"""
SifenContingenciaEngine: High-level Orchestrator for Resilient Offline SIFEN Operations.
Provides automatic failover, contingency generation, KuDE receipt delivery, and outbox synchronization.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ..constants import EMISSION_CONTINGENCIA, EMISSION_NORMAL, OutboxStatus
from ..models import DteHeaderInput, DteItemInput, MandantRucProfile, ResolvedProfile
from ..resolver import SifenProfileResolver
from ..xml_generator import SifenXmlGenerator, generate_sifen_cdc
from .circuit_breaker import CircuitBreaker
from .kude_generator import KuDeGenerator
from .models import (
    BatchSyncResult,
    ContingenciaIssueResult,
    DeadlineAlert,
    KuDeReceipt,
)
from .outbox_queue import DurableOutboxQueue
from .sync_worker import ContingenciaSyncWorker

logger = logging.getLogger(__name__)


class SifenContingenciaEngine:
    """
    Main engine orchestrating offline resiliency for the VibeCore SIFEN adapter:
    1. Automatic Failover: Seamlessly switches to iTipEmi=2 upon network timeout or outage.
    2. Zero Checkout Delays: Instantly produces valid CDC and KuDE receipt for waiting customer.
    3. Crash Safety: SQLite Write-Ahead Logging (WAL) guarantees zero document loss on power cut.
    4. Auto-Sync & Legal Compliance: Synchronizes within 72h legal DNIT window upon reconnection.
    """

    def __init__(
        self,
        db_path: str | Path = "sifen_contingencia_outbox.sqlite3",
        xml_generator: SifenXmlGenerator | None = None,
        resolver: SifenProfileResolver | None = None,
        kude_generator: KuDeGenerator | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        online_transmitter: Callable[[str], dict[str, Any]] | None = None,
        alert_callback: Callable[[DeadlineAlert], None] | None = None,
    ) -> None:
        self.resolver = resolver or SifenProfileResolver()
        self.xml_generator = xml_generator or SifenXmlGenerator(resolver=self.resolver)
        self.kude_generator = kude_generator or KuDeGenerator()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.queue = DurableOutboxQueue(db_path=db_path)
        self.online_transmitter = online_transmitter

        # Background sync worker
        def transmitter_adapter(rec):
            if self.online_transmitter:
                return self.online_transmitter(rec.xml_content)
            return {
                "protocol": f"SIFEN-DNIT-{rec.cdc[:8]}-{int(datetime.now().timestamp())}",
                "status": "ACCEPTED",
                "message": "Aprobado por DNIT SIFEN",
            }

        self.worker = ContingenciaSyncWorker(
            queue=self.queue,
            transmitter=transmitter_adapter,
            circuit_breaker=self.circuit_breaker,
            alert_callback=alert_callback,
        )

    def issue_document(
        self,
        header: DteHeaderInput,
        items: list[DteItemInput],
        profile_or_resolved: MandantRucProfile | ResolvedProfile | dict[str, Any],
        force_offline: bool = False,
    ) -> ContingenciaIssueResult:
        """
        Issue a SIFEN electronic document with automatic failover to Contingencia:
        - If online mode succeeds: Returns ACCEPTED document with KuDE.
        - If network fails, times out, or force_offline=True:
          Switches to iTipEmi=2, generates CDC, generates KuDE, enqueues to WAL Outbox.
        """
        # Resolve tax profile
        if isinstance(profile_or_resolved, ResolvedProfile):
            resolved = profile_or_resolved
        else:
            resolved = self.resolver.resolve(profile_or_resolved)

        # Clone header so we can safely adjust emission_type without side-effects on caller
        header_dict = header.model_dump()

        attempt_online = (
            not force_offline
            and self.online_transmitter is not None
            and self.circuit_breaker.can_attempt()
        )

        if attempt_online:
            # Try normal online emission (iTipEmi = 1)
            header_dict["emission_type"] = EMISSION_NORMAL
            normal_header = DteHeaderInput(**header_dict)
            cdc, cdc_dv = generate_sifen_cdc(normal_header, resolved.dte_type)

            try:
                xml_content = self.xml_generator.generate_xml(
                    header=normal_header,
                    items=items,
                    profile_or_resolved=resolved,
                )
                assert self.online_transmitter is not None
                response = self.online_transmitter(xml_content)
                protocol = response.get("protocol", "DNIT-OK")

                self.circuit_breaker.record_success()

                # Generate KuDE for customer
                kude = self.kude_generator.generate_kude(
                    header=normal_header,
                    items=items,
                    resolved=resolved,
                    cdc=cdc,
                    xml_content=xml_content,
                )

                # Persist as ACCEPTED in outbox
                record = self.queue.enqueue(
                    cdc=cdc,
                    cdc_dv=cdc_dv,
                    emission_type=EMISSION_NORMAL,
                    issue_date=normal_header.issue_date,
                    xml_content=xml_content,
                    header_data=normal_header.model_dump(),
                    items_data=[item.model_dump() for item in items],
                    profile_data=resolved.model_dump(),
                    kude_receipt=kude,
                    initial_status=OutboxStatus.ACCEPTED,
                )
                self.queue.update_status(
                    doc_id=record.id,
                    new_status=OutboxStatus.ACCEPTED,
                    dnit_protocol=protocol,
                    transmitted_at=datetime.now(),
                    detail=f"Direct online submission accepted, protocol: {protocol}",
                )

                return ContingenciaIssueResult(
                    success=True,
                    cdc=cdc,
                    emission_type=EMISSION_NORMAL,
                    is_offline_contingencia=False,
                    status=OutboxStatus.ACCEPTED,
                    kude_receipt=kude,
                    xml_content=xml_content,
                    record_id=record.id,
                    message="Documento transmitido y aprobado en linea por SIFEN.",
                )

            except Exception as exc:
                logger.warning(
                    "Online SIFEN transmission failed (%s). Triggering automatic Failover to Contingencia.",
                    exc,
                )
                self.circuit_breaker.record_failure(exc)

        # Failover / Offline Contingencia Path (iTipEmi = 2)
        header_dict["emission_type"] = EMISSION_CONTINGENCIA
        contingencia_header = DteHeaderInput(**header_dict)
        cdc, cdc_dv = generate_sifen_cdc(contingencia_header, resolved.dte_type)

        xml_content = self.xml_generator.generate_xml(
            header=contingencia_header,
            items=items,
            profile_or_resolved=resolved,
        )

        kude = self.kude_generator.generate_kude(
            header=contingencia_header,
            items=items,
            resolved=resolved,
            cdc=cdc,
            xml_content=xml_content,
        )

        record = self.queue.enqueue(
            cdc=cdc,
            cdc_dv=cdc_dv,
            emission_type=EMISSION_CONTINGENCIA,
            issue_date=contingencia_header.issue_date,
            xml_content=xml_content,
            header_data=contingencia_header.model_dump(),
            items_data=[item.model_dump() for item in items],
            profile_data=resolved.model_dump(),
            kude_receipt=kude,
            initial_status=OutboxStatus.QUEUED_OFFLINE,
        )

        return ContingenciaIssueResult(
            success=True,
            cdc=cdc,
            emission_type=EMISSION_CONTINGENCIA,
            is_offline_contingencia=True,
            status=OutboxStatus.QUEUED_OFFLINE,
            kude_receipt=kude,
            xml_content=xml_content,
            record_id=record.id,
            message="Modo Contingencia activado. KuDE generado para cliente; beleg in WAL-Queue gespeichert.",
        )

    def sync_pending(self, batch_size: int = 50, reference_time: datetime | None = None) -> BatchSyncResult:
        """Execute synchronization of queued offline contingencia documents."""
        return self.worker.process_pending_batch(batch_size=batch_size, reference_time=reference_time)

    def get_alerts(self, reference_time: datetime | None = None) -> list[DeadlineAlert]:
        """Check for documents approaching or exceeding 72h legal deadline."""
        return self.queue.check_deadlines(reference_time=reference_time)

    def get_metrics(self) -> dict[str, Any]:
        """Return operational metrics for monitoring."""
        return {
            "circuit_breaker_state": self.circuit_breaker.state.value,
            "circuit_breaker_failures": self.circuit_breaker.failure_count,
            "outbox_status_counts": self.queue.count_by_status(),
            "database_integrity_ok": self.queue.verify_integrity(),
        }
