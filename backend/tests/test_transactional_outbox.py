from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.crud.outbox_crud import enqueue_outbox_event
from app.db.base import CORE_SCHEMA
from app.models import OutboxEvent
from app.schemas.outbox_schemas import OutboxEventCreate, OutboxEventStatusUpdate


def _event_create_payload() -> dict[str, object]:
    return {
        "event_type": "journal_entry.posted",
        "event_version": 1,
        "aggregate_type": "journal_entry",
        "aggregate_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "idempotency_key": "journal-entry:example:posted:v1",
        "payload": {"data": {"journal_entry_id": "example"}},
    }


def test_outbox_model_uses_core_schema_and_required_delivery_fields() -> None:
    assert OutboxEvent.__table__.schema == CORE_SCHEMA
    assert OutboxEvent.__table__.name == "outbox_event"

    columns = OutboxEvent.__table__.c
    for column_name in (
        "id",
        "event_type",
        "payload",
        "status",
        "created_at",
        "processed_at",
    ):
        assert column_name in columns
    assert columns["payload"].type.__class__.__name__ == "JSONB"

    constraints = {constraint.name for constraint in OutboxEvent.__table__.constraints}
    assert "ck_outbox_event_status" in constraints
    assert "ck_outbox_event_processed_at_matches_status" in constraints


def test_outbox_create_schema_adds_compatible_payload_extension_points() -> None:
    event = OutboxEventCreate.model_validate(_event_create_payload())
    assert event.payload["meta"] == {}
    assert event.payload["custom_data"] == {}

    invalid = _event_create_payload()
    invalid["payload"] = {"meta": "not-an-object"}
    with pytest.raises(ValidationError, match="payload.meta"):
        OutboxEventCreate.model_validate(invalid)


def test_outbox_status_schema_requires_a_visible_failure_reason() -> None:
    with pytest.raises(ValidationError, match="require a failure_reason"):
        OutboxEventStatusUpdate.model_validate({"status": "FAILED"})

    failed = OutboxEventStatusUpdate.model_validate(
        {"status": "FAILED", "failure_reason": "adapter timeout"}
    )
    assert failed.status == "FAILED"


def test_enqueue_stages_event_without_committing_the_callers_transaction() -> None:
    class RecordingSession:
        def __init__(self) -> None:
            self.added: list[OutboxEvent] = []
            self.flushed = False
            self.committed = False

        def add(self, event: OutboxEvent) -> None:
            self.added.append(event)

        async def flush(self) -> None:
            self.flushed = True

        async def commit(self) -> None:
            self.committed = True

    session = RecordingSession()
    event = asyncio.run(enqueue_outbox_event(session, OutboxEventCreate(**_event_create_payload())))

    assert session.added == [event]
    assert session.flushed is True
    assert session.committed is False


def test_journal_post_stages_its_outbox_event_before_its_only_commit() -> None:
    source = Path("app/crud/accounting_crud.py").read_text()
    event_call = source.index("await enqueue_journal_entry_posted_event(session, journal_entry)")
    commit_call = source.index("await session.commit()", event_call)
    assert event_call < commit_call


def test_outbox_migration_registers_database_lifecycle_protection() -> None:
    migration = Path("migrations/versions/20260915_0004_create_transactional_outbox.py")
    source = migration.read_text()
    assert "core.outbox_event" in source
    assert "CREATE TRIGGER outbox_event_lifecycle_guard" in source
    assert "outbox event facts are immutable" in source
