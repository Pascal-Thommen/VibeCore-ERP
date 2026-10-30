"""
Business logic and persistent Outbox Queue orchestration for the SIFEN Fiscal Adapter.
Guarantees zero DTE loss on network failure and strict idempotency.
"""

import json
import logging
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from sifen.client import SifenClient, SifenError, SifenNetworkError, SifenNotFoundError
from sifen.config import Settings, settings
from sifen.db_models import SifenOutboxRecord
from sifen.models import (
    DteOutboxResponse,
    OutboxFlushResponse,
    OutboxStatus,
    SubmitDteRequest,
)
from sifen.resolver import SifenProfileResolver
from sifen.xml_generator import SifenXmlGenerator, generate_sifen_cdc

logger = logging.getLogger("sifen.service")


class SifenService:
    """Core service for SIFEN DTE generation, transmission, and persistent Outbox recovery."""

    def __init__(
        self,
        client: SifenClient | None = None,
        generator: SifenXmlGenerator | None = None,
        custom_settings: Settings | None = None,
    ) -> None:
        self.cfg = custom_settings or settings
        self.client = client or SifenClient(self.cfg)
        self.generator = generator or SifenXmlGenerator()

    @staticmethod
    def _record_to_response(record: SifenOutboxRecord) -> DteOutboxResponse:
        meta = json.loads(record.meta_json) if record.meta_json else None
        custom_data = (
            json.loads(record.custom_data_json) if record.custom_data_json else None
        )
        return DteOutboxResponse(
            cdc=record.cdc,
            dte_type=record.dte_type,
            issuer_ruc=record.issuer_ruc,
            document_number=record.document_number,
            total_amount=Decimal(record.total_amount),
            currency=record.currency,
            status=OutboxStatus(record.status),
            sifen_code=record.sifen_code,
            sifen_message=record.sifen_message,
            protocol_number=record.protocol_number,
            retry_count=record.retry_count,
            last_error=record.last_error,
            xml_payload=record.xml_payload,
            created_at=record.created_at,
            updated_at=record.updated_at,
            transmitted_at=record.transmitted_at,
            meta=meta,
            custom_data=custom_data,
        )

    @staticmethod
    def _extract_total_from_xml(xml_str: str) -> Decimal:
        root = ET.fromstring(xml_str.encode("utf-8"))
        tot_el = root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dTotGralOpe")
        if tot_el is not None and tot_el.text:
            return Decimal(tot_el.text.strip())
        return Decimal(0)

    async def submit_dte(
        self,
        db: Session,
        request: SubmitDteRequest,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> DteOutboxResponse:
        """
        Generates DTE XML, persists it in the local Outbox Queue, and attempts live SIFEN transmission.
        If a network timeout or upstream failure occurs, the DTE remains safely in QUEUED status.
        """
        if idempotency_key:
            existing_by_key = (
                db.query(SifenOutboxRecord)
                .filter(SifenOutboxRecord.idempotency_key == idempotency_key)
                .first()
            )
            if existing_by_key:
                return self._record_to_response(existing_by_key)

        resolved = SifenProfileResolver.resolve(request.profile)
        cdc, _ = generate_sifen_cdc(request.header, resolved.dte_type)

        existing_by_cdc = (
            db.query(SifenOutboxRecord)
            .filter(SifenOutboxRecord.cdc == cdc)
            .first()
        )
        if existing_by_cdc:
            return self._record_to_response(existing_by_cdc)

        xml_payload = self.generator.generate_xml(
            header=request.header,
            items=request.items,
            profile_or_resolved=resolved,
            pretty=True,
        )
        total_amount = self._extract_total_from_xml(xml_payload)

        now = datetime.now(UTC)
        record = SifenOutboxRecord(
            cdc=cdc,
            idempotency_key=idempotency_key,
            dte_type=resolved.dte_type,
            issuer_ruc=request.header.issuer_ruc,
            document_number=request.header.document_number,
            total_amount=str(total_amount),
            currency=request.header.currency,
            status=OutboxStatus.QUEUED.value,
            xml_payload=xml_payload,
            retry_count=0,
            meta_json=json.dumps(request.meta) if request.meta is not None else None,
            custom_data_json=(
                json.dumps(request.custom_data)
                if request.custom_data is not None
                else None
            ),
            created_at=now,
            updated_at=now,
        )

        try:
            db.add(record)
            db.commit()
            db.refresh(record)
        except Exception as exc:
            db.rollback()
            raise SifenError(f"Database error persisting outbox DTE: {exc}") from exc

        await self._attempt_transmission(db, record, correlation_id=correlation_id)
        return self._record_to_response(record)

    async def _attempt_transmission(
        self,
        db: Session,
        record: SifenOutboxRecord,
        correlation_id: str | None = None,
    ) -> None:
        """Attempts to transmit a single outbox record, updating its state in SQLite."""
        try:
            result = await self.client.transmit_dte(
                cdc=record.cdc,
                dte_xml=record.xml_payload,
                correlation_id=correlation_id,
            )
            now = datetime.now(UTC)
            record.status = (
                OutboxStatus.ACCEPTED.value
                if result["accepted"]
                else OutboxStatus.REJECTED.value
            )
            record.sifen_code = result["sifen_code"]
            record.sifen_message = result["sifen_message"]
            record.protocol_number = result.get("protocol_number")
            record.last_error = None
            record.transmitted_at = now
            record.updated_at = now
            db.commit()
            db.refresh(record)
        except SifenNetworkError as exc:
            logger.warning(
                "DTE cdc=%s kept in persistent outbox queue due to network error: %s",
                record.cdc,
                exc,
            )
            record.status = OutboxStatus.QUEUED.value
            record.retry_count += 1
            record.last_error = str(exc)
            record.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(record)

    async def flush_outbox(
        self,
        db: Session,
        correlation_id: str | None = None,
    ) -> OutboxFlushResponse:
        """
        Retries all QUEUED DTE records in the persistent outbox in FIFO order.
        """
        queued_records = (
            db.query(SifenOutboxRecord)
            .filter(SifenOutboxRecord.status == OutboxStatus.QUEUED.value)
            .order_by(SifenOutboxRecord.created_at.asc(), SifenOutboxRecord.id.asc())
            .all()
        )

        accepted_count = 0
        rejected_count = 0
        still_queued_count = 0
        items: list[DteOutboxResponse] = []

        for record in queued_records:
            await self._attempt_transmission(db, record, correlation_id=correlation_id)
            if record.status == OutboxStatus.ACCEPTED.value:
                accepted_count += 1
            elif record.status == OutboxStatus.REJECTED.value:
                rejected_count += 1
            else:
                still_queued_count += 1
            items.append(self._record_to_response(record))

        return OutboxFlushResponse(
            processed_count=len(queued_records),
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            still_queued_count=still_queued_count,
            items=items,
        )

    def get_by_cdc(self, db: Session, cdc: str) -> DteOutboxResponse:
        record = (
            db.query(SifenOutboxRecord)
            .filter(SifenOutboxRecord.cdc == cdc)
            .first()
        )
        if not record:
            raise SifenNotFoundError(f"DTE with CDC '{cdc}' not found in outbox")
        return self._record_to_response(record)

    def list_outbox(
        self, db: Session, status_filter: str | None = None
    ) -> list[DteOutboxResponse]:
        query = db.query(SifenOutboxRecord)
        if status_filter:
            query = query.filter(SifenOutboxRecord.status == status_filter.upper())
        records = query.order_by(SifenOutboxRecord.created_at.desc()).all()
        return [self._record_to_response(r) for r in records]
