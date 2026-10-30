"""
SQLAlchemy ORM models for the SIFEN persistent Outbox Queue.
Ensures zero DTE loss during DNIT/SET network outages and strict idempotency.
"""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class SifenOutboxRecord(Base):
    __tablename__ = "sifen_outbox"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cdc = Column(String(44), unique=True, index=True, nullable=False)
    idempotency_key = Column(String(100), unique=True, index=True, nullable=True)
    dte_type = Column(Integer, nullable=False)
    issuer_ruc = Column(String(20), nullable=False, index=True)
    document_number = Column(String(20), nullable=False)
    total_amount = Column(String(50), nullable=False)
    currency = Column(String(10), default="PYG", nullable=False)

    status = Column(String(30), default="QUEUED", nullable=False, index=True)
    xml_payload = Column(Text, nullable=False)

    sifen_code = Column(String(20), nullable=True)
    sifen_message = Column(Text, nullable=True)
    protocol_number = Column(String(100), nullable=True)

    retry_count = Column(Integer, default=0, nullable=False)
    last_error = Column(Text, nullable=True)
    meta_json = Column(Text, nullable=True)
    custom_data_json = Column(Text, nullable=True)

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
    transmitted_at = Column(DateTime, nullable=True)
