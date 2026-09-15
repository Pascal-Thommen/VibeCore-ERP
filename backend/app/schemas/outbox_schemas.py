"""Pydantic contracts for transactional-outbox creation and delivery state."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    model_validator,
)

from app.schemas.core_schemas import CoreReadSchema, CoreSchema

OutboxEventStatus = Literal["PENDING", "PROCESSING", "PROCESSED", "FAILED"]
EventType = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]
AggregateType = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]
IdempotencyKey = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=255)]
FailureReason = Annotated[
    str | None, StringConstraints(strict=True, min_length=1, max_length=4_000)
]


class OutboxEventCreate(CoreSchema):
    """Immutable facts for an event staged in the caller's current transaction."""

    event_type: EventType
    event_version: Annotated[int, Field(ge=1)] = 1
    aggregate_type: AggregateType
    aggregate_id: UUID
    correlation_id: UUID
    idempotency_key: IdempotencyKey
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def add_payload_extension_points(self) -> OutboxEventCreate:
        """Keep Core-to-adapter payload evolution compatible by default."""
        meta = self.payload.get("meta", {})
        custom_data = self.payload.get("custom_data", {})
        if not isinstance(meta, dict):
            raise ValueError("payload.meta must be an object when provided")
        if not isinstance(custom_data, dict):
            raise ValueError("payload.custom_data must be an object when provided")
        # CoreSchema validates assignment.  Bypass assignment validation here to
        # avoid recursively invoking this model validator after values were
        # already fully validated.
        object.__setattr__(
            self, "payload", {"meta": meta, "custom_data": custom_data, **self.payload}
        )
        return self


class OutboxDeliveryStateSchema(BaseModel):
    """Strict schema base that exposes no immutable event-fact fields."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class OutboxEventStatusUpdate(OutboxDeliveryStateSchema):
    """The only application-level mutation accepted for an outbox event."""

    status: OutboxEventStatus
    failure_reason: FailureReason = None

    @model_validator(mode="after")
    def validate_failure_reason(self) -> OutboxEventStatusUpdate:
        if self.status == "FAILED" and self.failure_reason is None:
            raise ValueError("FAILED outbox events require a failure_reason")
        if self.status != "FAILED" and self.failure_reason is not None:
            raise ValueError("failure_reason may only be supplied for FAILED outbox events")
        return self


class OutboxEventRead(CoreReadSchema):
    event_type: str
    event_version: int
    aggregate_type: str
    aggregate_id: UUID
    correlation_id: UUID
    idempotency_key: str
    payload: dict[str, JsonValue]
    status: OutboxEventStatus
    attempt_count: int
    last_attempt_at: datetime | None
    last_error: str | None
    processed_at: datetime | None
