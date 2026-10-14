"""
Pydantic data models for SIFEN Contingencia & Durable Outbox Queue.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..models import DteHeaderInput, DteItemInput, MandantRucProfile, ResolvedProfile
from .enums import AlertSeverity, OutboxStatus


class KuDeReceipt(BaseModel):
    """
    KuDE (Kuatia Yahechaukaha Digital - KuDE) representation and customer receipt.
    Complies with DNIT / SET SIFEN Technical Manual Version 150.
    """

    model_config = ConfigDict(extra="ignore")

    cdc: str = Field(description="44-digit official SIFEN CDC")
    cdc_formatted: str = Field(description="4-digit grouped formatted CDC")
    timbrado: str
    establishment_code: str
    point_of_issue_code: str
    document_number: str
    emission_type: int
    is_contingencia: bool
    issue_date: datetime
    issuer_name: str
    issuer_ruc: str
    receiver_name: str
    receiver_id: str
    total_operation: Decimal
    total_iva: Decimal
    qr_url: str = Field(description="Official SIFEN QR query URL")
    qr_data_uri: str = Field(default="", description="Base64/SVG data URI of QR code")
    qr_ascii: str = Field(default="", description="ASCII art QR code for terminal/thermal printers")
    receipt_text: str = Field(description="Formatted thermal POS receipt printout")


class ContingenciaRecord(BaseModel):
    """
    Durable Outbox Queue item stored in SQLite WAL persistence.
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(description="Unique outbox record ID (UUID)")
    cdc: str = Field(description="44-digit official SIFEN CDC")
    cdc_dv: str = Field(description="Check digit (DV) of CDC")
    emission_type: int = Field(description="1=Normal, 2=Contingencia")
    status: OutboxStatus = Field(default=OutboxStatus.QUEUED_OFFLINE)
    created_at: datetime
    issue_date: datetime
    xml_content: str
    kude_receipt: KuDeReceipt | None = None
    header_data: dict[str, Any]
    items_data: list[dict[str, Any]]
    profile_data: dict[str, Any]
    retry_count: int = 0
    next_retry_at: datetime | None = None
    last_error: str | None = None
    transmitted_at: datetime | None = None
    dnit_protocol: str | None = None

    @property
    def hours_elapsed(self) -> float:
        """Hours elapsed since document issue date."""
        return (datetime.now() - self.issue_date).total_seconds() / 3600.0

    @property
    def hours_until_deadline(self) -> float:
        """Hours remaining until legal 72h contingencia deadline."""
        return 72.0 - self.hours_elapsed

    @property
    def is_expired(self) -> bool:
        """True if the document exceeded the 72h legal submission window."""
        return self.hours_until_deadline <= 0.0


class DeadlineAlert(BaseModel):
    """
    Alert triggered when a contingencia document approaches or exceeds the 72h limit.
    """

    model_config = ConfigDict(extra="ignore")

    document_id: str
    cdc: str
    issue_date: datetime
    hours_remaining: float
    severity: AlertSeverity
    message: str


class BatchSyncResult(BaseModel):
    """
    Summary result of an asynchronous or batch synchronization run.
    """

    model_config = ConfigDict(extra="ignore")

    total_scanned: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    retry_count: int = 0
    expired_count: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)


class ContingenciaIssueResult(BaseModel):
    """
    Result returned to caller upon issuing a document.
    Ensures local POS receives immediate KuDE receipt and CDC regardless of network status.
    """

    model_config = ConfigDict(extra="ignore")

    success: bool
    cdc: str
    emission_type: int
    is_offline_contingencia: bool
    status: OutboxStatus
    kude_receipt: KuDeReceipt
    xml_content: str
    record_id: str
    message: str
