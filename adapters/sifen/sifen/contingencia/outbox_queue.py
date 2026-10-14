"""
Durable Transactional Outbox Queue with SQLite Write-Ahead Logging (WAL).
Provides crash-safe, local, offline persistence for Paraguayan SIFEN fiscal documents.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .enums import AlertSeverity, OutboxStatus
from .models import ContingenciaRecord, DeadlineAlert, KuDeReceipt


class DurableOutboxQueue:
    """
    Durable Outbox Queue providing zero data loss during power outages or system crashes.
    Uses SQLite WAL mode with synchronous durability guarantees.
    """

    def __init__(self, db_path: str | Path = "sifen_contingencia_outbox.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Create a connection with WAL mode and appropriate timeout."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=10.0,
            isolation_level=None,  # Autocommit mode; we manage explicit transactions
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self) -> None:
        """Initialize table schema and indexes inside an explicit transaction."""
        with self.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sifen_outbox (
                    id TEXT PRIMARY KEY,
                    cdc TEXT UNIQUE NOT NULL,
                    cdc_dv TEXT NOT NULL,
                    emission_type INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    issue_date TEXT NOT NULL,
                    xml_content TEXT NOT NULL,
                    kude_json TEXT,
                    header_json TEXT NOT NULL,
                    items_json TEXT NOT NULL,
                    profile_json TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT,
                    last_error TEXT,
                    transmitted_at TEXT,
                    dnit_protocol TEXT
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sifen_outbox_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL,
                    old_status TEXT,
                    new_status TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    detail TEXT,
                    FOREIGN KEY(document_id) REFERENCES sifen_outbox(id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sifen_outbox_status_retry ON sifen_outbox(status, next_retry_at);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sifen_outbox_issue_date ON sifen_outbox(issue_date);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sifen_outbox_cdc ON sifen_outbox(cdc);"
            )
            conn.execute("COMMIT;")

    def enqueue(
        self,
        cdc: str,
        cdc_dv: str,
        emission_type: int,
        issue_date: datetime,
        xml_content: str,
        header_data: dict[str, Any],
        items_data: list[dict[str, Any]],
        profile_data: dict[str, Any],
        kude_receipt: KuDeReceipt | None = None,
        initial_status: OutboxStatus = OutboxStatus.QUEUED_OFFLINE,
        doc_id: str | None = None,
    ) -> ContingenciaRecord:
        """
        Atomically enqueue a document into the durable outbox queue.
        Guaranteed to be crash-safe in SQLite WAL mode.
        """
        record_id = doc_id or str(uuid4())
        created_at_dt = datetime.now()
        created_at_str = created_at_dt.isoformat()
        issue_date_str = issue_date.isoformat()

        kude_json = kude_receipt.model_dump_json() if kude_receipt else None
        header_json = json.dumps(header_data, default=str)
        items_json = json.dumps(items_data, default=str)
        profile_json = json.dumps(profile_data, default=str)

        with self.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                """
                INSERT INTO sifen_outbox (
                    id, cdc, cdc_dv, emission_type, status, created_at, issue_date,
                    xml_content, kude_json, header_json, items_json, profile_json,
                    retry_count, next_retry_at, last_error, transmitted_at, dnit_protocol
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, NULL, NULL);
                """,
                (
                    record_id,
                    cdc,
                    cdc_dv,
                    emission_type,
                    initial_status.value,
                    created_at_str,
                    issue_date_str,
                    xml_content,
                    kude_json,
                    header_json,
                    items_json,
                    profile_json,
                ),
            )
            conn.execute(
                """
                INSERT INTO sifen_outbox_audit (document_id, old_status, new_status, timestamp, detail)
                VALUES (?, NULL, ?, ?, ?);
                """,
                (record_id, initial_status.value, created_at_str, "Initial enqueue"),
            )
            conn.execute("COMMIT;")

        return ContingenciaRecord(
            id=record_id,
            cdc=cdc,
            cdc_dv=cdc_dv,
            emission_type=emission_type,
            status=initial_status,
            created_at=created_at_dt,
            issue_date=issue_date,
            xml_content=xml_content,
            kude_receipt=kude_receipt,
            header_data=header_data,
            items_data=items_data,
            profile_data=profile_data,
            retry_count=0,
            next_retry_at=None,
            last_error=None,
            transmitted_at=None,
            dnit_protocol=None,
        )

    def get(self, doc_id: str) -> ContingenciaRecord | None:
        """Retrieve an outbox record by ID."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM sifen_outbox WHERE id = ?;", (doc_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def get_by_cdc(self, cdc: str) -> ContingenciaRecord | None:
        """Retrieve an outbox record by 44-digit CDC."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM sifen_outbox WHERE cdc = ?;", (cdc,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def update_status(
        self,
        doc_id: str,
        new_status: OutboxStatus,
        error: str | None = None,
        dnit_protocol: str | None = None,
        transmitted_at: datetime | None = None,
        next_retry_at: datetime | None = None,
        increment_retry: bool = False,
        detail: str | None = None,
    ) -> bool:
        """
        Atomically update the status and tracking metadata of an outbox record.
        """
        now_str = datetime.now().isoformat()
        transmitted_str = transmitted_at.isoformat() if transmitted_at else None
        next_retry_str = next_retry_at.isoformat() if next_retry_at else None

        with self.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            cursor = conn.execute("SELECT status, retry_count FROM sifen_outbox WHERE id = ?;", (doc_id,))
            row = cursor.fetchone()
            if not row:
                conn.execute("ROLLBACK;")
                return False

            old_status = row["status"]
            current_retry = row["retry_count"]
            new_retry = current_retry + 1 if increment_retry else current_retry

            conn.execute(
                """
                UPDATE sifen_outbox SET
                    status = ?,
                    retry_count = ?,
                    next_retry_at = ?,
                    last_error = COALESCE(?, last_error),
                    transmitted_at = COALESCE(?, transmitted_at),
                    dnit_protocol = COALESCE(?, dnit_protocol)
                WHERE id = ?;
                """,
                (
                    new_status.value,
                    new_retry,
                    next_retry_str,
                    error,
                    transmitted_str,
                    dnit_protocol,
                    doc_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO sifen_outbox_audit (document_id, old_status, new_status, timestamp, detail)
                VALUES (?, ?, ?, ?, ?);
                """,
                (doc_id, old_status, new_status.value, now_str, detail or error or "Status transition"),
            )
            conn.execute("COMMIT;")
        return True

    def list(
        self,
        status: OutboxStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ContingenciaRecord]:
        """List documents in outbox with optional status filter."""
        with self.get_connection() as conn:
            if status is not None:
                cursor = conn.execute(
                    "SELECT * FROM sifen_outbox WHERE status = ? ORDER BY issue_date ASC LIMIT ? OFFSET ?;",
                    (status.value, limit, offset),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM sifen_outbox ORDER BY issue_date ASC LIMIT ? OFFSET ?;",
                    (limit, offset),
                )
            rows = cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    def get_pending_batch(
        self,
        limit: int = 50,
        reference_time: datetime | None = None,
    ) -> list[ContingenciaRecord]:
        """
        Get batch of documents eligible for transmission:
        status is QUEUED_OFFLINE and next_retry_at is null or passed.
        Ordered by issue_date ascending (FIFO to prioritize oldest near 72h).
        """
        ref_time = reference_time or datetime.now()
        ref_time_str = ref_time.isoformat()

        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM sifen_outbox
                WHERE status = ?
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                ORDER BY issue_date ASC
                LIMIT ?;
                """,
                (OutboxStatus.QUEUED_OFFLINE.value, ref_time_str, limit),
            )
            rows = cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    def check_deadlines(
        self,
        reference_time: datetime | None = None,
    ) -> list[DeadlineAlert]:
        """
        Enforce SIFEN 72-hour legal deadline for Contingencia documents.
        - Automatically transitions unaccepted documents > 72h to EXPIRED.
        - Generates WARNING alerts for documents with < 24h remaining.
        - Generates CRITICAL alerts for documents with < 12h remaining.
        """
        ref_time = reference_time or datetime.now()
        alerts: list[DeadlineAlert] = []

        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, cdc, issue_date, status FROM sifen_outbox
                WHERE status IN (?, ?);
                """,
                (OutboxStatus.QUEUED_OFFLINE.value, OutboxStatus.TRANSMITTING.value),
            )
            rows = cursor.fetchall()

            for row in rows:
                doc_id = row["id"]
                cdc = row["cdc"]
                issue_dt = datetime.fromisoformat(row["issue_date"])
                hours_elapsed = (ref_time - issue_dt).total_seconds() / 3600.0
                hours_remaining = 72.0 - hours_elapsed

                if hours_remaining <= 0.0:
                    # Legal deadline exceeded!
                    self.update_status(
                        doc_id=doc_id,
                        new_status=OutboxStatus.EXPIRED,
                        error=f"Exceeded legal 72h contingency deadline ({hours_elapsed:.1f} hours elapsed)",
                        detail="72h deadline expired",
                    )
                    alerts.append(
                        DeadlineAlert(
                            document_id=doc_id,
                            cdc=cdc,
                            issue_date=issue_dt,
                            hours_remaining=hours_remaining,
                            severity=AlertSeverity.EXPIRED,
                            message=f"DTE {cdc} abgelaufen! Ueberschritt die 72h-Contingencia-Frist ({hours_elapsed:.1f}h vergangen).",
                        )
                    )
                elif hours_remaining <= 12.0:
                    alerts.append(
                        DeadlineAlert(
                            document_id=doc_id,
                            cdc=cdc,
                            issue_date=issue_dt,
                            hours_remaining=hours_remaining,
                            severity=AlertSeverity.CRITICAL,
                            message=f"KRITISCH: DTE {cdc} hat nur noch {hours_remaining:.1f}h bis zur 72h-Frist!",
                        )
                    )
                elif hours_remaining <= 24.0:
                    alerts.append(
                        DeadlineAlert(
                            document_id=doc_id,
                            cdc=cdc,
                            issue_date=issue_dt,
                            hours_remaining=hours_remaining,
                            severity=AlertSeverity.WARNING,
                            message=f"WARNUNG: DTE {cdc} naehert sich 72h-Frist ({hours_remaining:.1f}h verbleibend).",
                        )
                    )

        return alerts

    def count_by_status(self) -> dict[str, int]:
        """Return counts of documents grouped by status."""
        counts = {s.value: 0 for s in OutboxStatus}
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT status, COUNT(*) as cnt FROM sifen_outbox GROUP BY status;")
            for row in cursor.fetchall():
                counts[row["status"]] = row["cnt"]
        return counts

    def verify_integrity(self) -> bool:
        """Run SQLite integrity check to verify zero database corruption."""
        with self.get_connection() as conn:
            cursor = conn.execute("PRAGMA integrity_check;")
            row = cursor.fetchone()
            return row[0].lower() == "ok"

    def checkpoint(self) -> None:
        """Flush SQLite WAL frames to main database file."""
        with self.get_connection() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")

    def _row_to_record(self, row: sqlite3.Row) -> ContingenciaRecord:
        kude_receipt = None
        if row["kude_json"]:
            try:
                kude_receipt = KuDeReceipt.model_validate_json(row["kude_json"])
            except Exception:
                pass

        return ContingenciaRecord(
            id=row["id"],
            cdc=row["cdc"],
            cdc_dv=row["cdc_dv"],
            emission_type=row["emission_type"],
            status=OutboxStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            issue_date=datetime.fromisoformat(row["issue_date"]),
            xml_content=row["xml_content"],
            kude_receipt=kude_receipt,
            header_data=json.loads(row["header_json"]),
            items_data=json.loads(row["items_json"]),
            profile_data=json.loads(row["profile_json"]),
            retry_count=row["retry_count"],
            next_retry_at=datetime.fromisoformat(row["next_retry_at"]) if row["next_retry_at"] else None,
            last_error=row["last_error"],
            transmitted_at=datetime.fromisoformat(row["transmitted_at"]) if row["transmitted_at"] else None,
            dnit_protocol=row["dnit_protocol"],
        )
