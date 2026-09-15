"""Transactional-outbox persistence operations.

``enqueue_outbox_event`` deliberately does not commit.  A domain operation
stages its state change and event in one SQLAlchemy session, then commits them
once.  This is the ACID boundary required by the transactional-outbox pattern.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JournalEntry, OutboxEvent
from app.schemas.outbox_schemas import OutboxEventCreate, OutboxEventStatusUpdate


class OutboxEventStateError(Exception):
    """Raised when a delivery-state transition would violate the outbox lifecycle."""


_VALID_STATUS_TRANSITIONS = {
    "PENDING": {"PROCESSING"},
    "PROCESSING": {"PENDING", "PROCESSED", "FAILED"},
    "FAILED": {"PENDING"},
    "PROCESSED": set(),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def enqueue_outbox_event(session: AsyncSession, data: OutboxEventCreate) -> OutboxEvent:
    """Stage an event without committing the transaction that owns it."""
    event = OutboxEvent(**data.model_dump(by_alias=False))
    session.add(event)
    await session.flush()
    return event


async def enqueue_journal_entry_posted_event(
    session: AsyncSession, journal_entry: JournalEntry
) -> OutboxEvent:
    """Stage the integration fact emitted by a successful journal posting."""
    return await enqueue_outbox_event(
        session,
        OutboxEventCreate(
            event_type="journal_entry.posted",
            event_version=1,
            aggregate_type="journal_entry",
            aggregate_id=journal_entry.id,
            correlation_id=journal_entry.id,
            idempotency_key=f"journal-entry:{journal_entry.id}:posted:v1",
            payload={
                "data": {
                    "journal_entry_id": str(journal_entry.id),
                    "entry_date": journal_entry.entry_date.isoformat(),
                    "reference": journal_entry.reference,
                    "source_document_id": (
                        str(journal_entry.source_document_id)
                        if journal_entry.source_document_id is not None
                        else None
                    ),
                    "status": "POSTED",
                },
            },
        ),
    )


async def get_outbox_event(session: AsyncSession, event_id: UUID) -> OutboxEvent | None:
    """Return one event by immutable event identifier."""
    return await session.get(OutboxEvent, event_id)


async def list_pending_outbox_events(
    session: AsyncSession, *, limit: int = 100
) -> list[OutboxEvent]:
    """Fetch pending events in publication order; polling is recovery-only."""
    statement = (
        select(OutboxEvent)
        .where(OutboxEvent.status == "PENDING")
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(limit)
    )
    return list(await session.scalars(statement))


async def update_outbox_event_status(
    session: AsyncSession,
    event_id: UUID,
    data: OutboxEventStatusUpdate,
) -> OutboxEvent | None:
    """Persist a validated delivery transition for one outstanding event."""
    statement = select(OutboxEvent).where(OutboxEvent.id == event_id).with_for_update()
    event = (await session.scalars(statement)).one_or_none()
    if event is None:
        return None

    if data.status not in _VALID_STATUS_TRANSITIONS[event.status]:
        raise OutboxEventStateError(
            f"invalid outbox event lifecycle transition from {event.status} to {data.status}"
        )

    now = _utc_now()
    if data.status == "PROCESSING":
        event.attempt_count += 1
        event.last_attempt_at = now
        event.last_error = None
    elif data.status == "PROCESSED":
        event.processed_at = now
        event.last_error = None
    elif data.status == "FAILED":
        event.last_error = data.failure_reason
    else:  # PROCESSING or FAILED was returned to the recovery queue.
        event.last_error = None

    event.status = data.status
    await session.commit()
    await session.refresh(event)
    return event


async def claim_pending_outbox_events(
    session: AsyncSession, *, limit: int = 100
) -> list[OutboxEvent]:
    """Atomically claim pending work for a publisher without waiting on peers."""
    statement = (
        select(OutboxEvent)
        .where(OutboxEvent.status == "PENDING")
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    events = list(await session.scalars(statement))
    if not events:
        return []

    now = _utc_now()
    for event in events:
        event.status = "PROCESSING"
        event.attempt_count += 1
        event.last_attempt_at = now
        event.last_error = None
    await session.commit()
    for event in events:
        await session.refresh(event)
    return events
