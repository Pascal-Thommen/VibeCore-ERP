"""
SQLAlchemy ORM models for Stripe transaction persistence and audit log.
Provides ACID guarantees, idempotency tracking and replay defense.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class StripeTransaction(Base):
    __tablename__ = "stripe_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(100), unique=True, index=True, nullable=False)
    idempotency_key = Column(String(100), index=True, nullable=True)
    stripe_id = Column(String(100), unique=True, index=True, nullable=False)
    payment_intent_id = Column(String(100), index=True, nullable=True)
    payment_type = Column(String(50), nullable=False)  # "checkout_session" or "payment_intent"
    status = Column(String(50), default="INITIATED", nullable=False, index=True)
    amount = Column(Float, nullable=False)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)

    customer_email = Column(String(255), nullable=True)
    description = Column(Text, nullable=False)
    checkout_url = Column(String(500), nullable=True)
    client_secret = Column(String(255), nullable=True)
    receipt_url = Column(String(500), nullable=True)
    payment_method = Column(String(100), nullable=True)
    failure_reason = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    paid_at = Column(DateTime, nullable=True)

    raw_order_payload = Column(Text, nullable=True)
    raw_last_response = Column(Text, nullable=True)


class StripeWebhookLog(Base):
    __tablename__ = "stripe_webhook_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(100), index=True, nullable=False)
    event_type = Column(String(100), index=True, nullable=False)
    stripe_object_id = Column(String(100), index=True, nullable=True)
    received_signature = Column(String(255), nullable=False)
    calculated_signature = Column(String(255), nullable=False)
    is_valid_signature = Column(Boolean, nullable=False)
    processed_status = Column(String(50), nullable=False)  # "PROCESSED", "DUPLICATE_IGNORED", "SIGNATURE_FAILED", "UNHANDLED_EVENT"
    raw_payload = Column(Text, nullable=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
