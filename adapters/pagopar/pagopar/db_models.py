"""
SQLAlchemy ORM models for Pagopar transaction persistence and audit log.
Provides ACID guarantees, idempotency tracking and replay defense.
"""

from datetime import datetime, timezone
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


class PagoparTransaction(Base):
    __tablename__ = "pagopar_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(100), unique=True, index=True, nullable=False)
    idempotency_key = Column(String(100), index=True, nullable=True)
    pagopar_hash = Column(String(100), unique=True, index=True, nullable=True)
    status = Column(String(50), default="INITIATED", nullable=False, index=True)
    monto_total = Column(Float, nullable=False)
    currency = Column(String(10), default="PYG", nullable=False)

    buyer_email = Column(String(255), nullable=False)
    buyer_ruc = Column(String(50), nullable=False)
    buyer_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    checkout_url = Column(String(500), nullable=True)

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    paid_at = Column(DateTime, nullable=True)
    payment_method = Column(String(100), nullable=True)
    receipt_number = Column(String(100), nullable=True)

    raw_order_payload = Column(Text, nullable=True)
    raw_last_response = Column(Text, nullable=True)


class PagoparWebhookLog(Base):
    __tablename__ = "pagopar_webhook_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    hash_pedido = Column(String(100), index=True, nullable=False)
    identificador_pago = Column(Integer, nullable=True, index=True)
    received_token = Column(String(100), nullable=False)
    calculated_token = Column(String(100), nullable=False)
    is_valid_signature = Column(Boolean, nullable=False)
    is_paid = Column(Boolean, nullable=False)
    amount = Column(Float, nullable=False)
    processed_status = Column(String(50), nullable=False)
    raw_payload = Column(Text, nullable=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
