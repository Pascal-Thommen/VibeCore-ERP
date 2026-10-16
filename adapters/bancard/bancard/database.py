"""Database models and persistence layer for Bancard Adapter."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from bancard.config import settings
from bancard.constants import TransactionStatus


class Base(DeclarativeBase):
    pass


class BancardTransaction(Base):
    __tablename__ = "bancard_transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idempotency_key = Column(String(128), unique=True, index=True, nullable=True)
    shop_process_id = Column(BigInteger, unique=True, index=True, nullable=False)
    user_id = Column(String(128), index=True, nullable=True)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="PYG")
    payment_method = Column(String(32), nullable=False)
    status = Column(String(20), nullable=False, default=TransactionStatus.PENDING.value, index=True)
    description = Column(Text, nullable=True)
    bancard_token = Column(String(128), nullable=True)
    bancard_process_id = Column(String(128), nullable=True)
    alias_token = Column(String(128), nullable=True)
    response_code = Column(String(10), nullable=True)
    response_description = Column(Text, nullable=True)
    ticket_number = Column(String(64), nullable=True)
    authorization_number = Column(String(64), nullable=True)
    qr_payload = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    raw_request = Column(JSON, nullable=True)
    raw_response = Column(JSON, nullable=True)

    audit_logs = relationship("TransactionAuditLog", back_populates="transaction", cascade="all, delete-orphan")


class TransactionAuditLog(Base):
    __tablename__ = "transaction_audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transaction_id = Column(String(36), ForeignKey("bancard_transactions.id"), nullable=False, index=True)
    shop_process_id = Column(BigInteger, nullable=False, index=True)
    previous_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)
    reason = Column(String(255), nullable=True)
    actor = Column(String(64), nullable=False, default="system")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    details = Column(JSON, nullable=True)

    transaction = relationship("BancardTransaction", back_populates="audit_logs")


class DeadLetterWebhook(Base):
    __tablename__ = "dead_letter_webhooks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    target_url = Column(String(512), nullable=False)
    event_type = Column(String(64), nullable=False)
    payload = Column(Text, nullable=False)
    signature = Column(String(256), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="FAILED", index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


# Configure Engine and Session factory
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency for providing database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
