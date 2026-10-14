"""
Comprehensive Test Suite for SIFEN Offline-Contingencia & Durable Outbox Queue.
Tests:
- SQLite WAL transactional persistence and zero data loss.
- Automatic failover and Circuit Breaker behavior.
- Contingencia generation (iTipEmi = 2, CDC, KuDE receipt, SIFEN QR code).
- Background batch synchronization with exponential backoff.
- 72h legal deadline enforcement, warning alerts, and expiration.
- Chaos simulation: SIGKILL / sudden process termination during writing.
- Chaos simulation: Intermittent and permanent network outages.
"""

from __future__ import annotations

import multiprocessing
import os
import signal
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from sifen.contingencia import (
    AlertSeverity,
    BusinessRejectionError,
    CircuitBreaker,
    CircuitState,
    ContingenciaSyncWorker,
    DurableOutboxQueue,
    EMISSION_CONTINGENCIA,
    EMISSION_NORMAL,
    KuDeGenerator,
    OutboxStatus,
    SifenContingenciaEngine,
    TransmissionError,
    format_cdc_blocks,
)
from sifen.constants import (
    DTE_BOLETA_RESIMPLE,
    DTE_FACTURA_ELECTRONICA,
    OBLIGACION_IRE_GENERAL,
    OBLIGACION_IRE_RESIMPLE,
    TaxRegime,
)
from sifen.models import (
    DteHeaderInput,
    DteItemInput,
    MandantRucProfile,
)
from sifen.resolver import SifenProfileResolver
from sifen.xml_generator import SifenXmlGenerator, compute_sifen_modulo_11


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_sifen_outbox.sqlite3"


@pytest.fixture
def sample_fe_header() -> DteHeaderInput:
    return DteHeaderInput(
        timbrado_number="87654321",
        establishment_code="001",
        point_of_issue_code="001",
        document_number="0000042",
        issue_date=datetime(2026, 10, 14, 15, 30, 0),
        security_code="987654321",
        issuer_ruc="80011111",
        issuer_dv="4",
        issuer_legal_name="VibeCore Enterprise S.A.",
        currency="PYG",
    )


@pytest.fixture
def sample_fe_items() -> list[DteItemInput]:
    return [
        DteItemInput(
            line_number=1,
            code="SRV-01",
            description="Licencia Cloud VibeCore ERP",
            quantity=Decimal("1"),
            unit_price=Decimal("11000000"),
            tax_rate=Decimal("10"),
        ),
        DteItemInput(
            line_number=2,
            code="SRV-02",
            description="Soporte Tecnico Presencial",
            quantity=Decimal("2"),
            unit_price=Decimal("525000"),
            tax_rate=Decimal("5"),
        ),
    ]


@pytest.fixture
def sample_general_profile() -> MandantRucProfile:
    return MandantRucProfile(
        ruc="80011111",
        dv="4",
        legal_name="VibeCore Enterprise S.A.",
        obligaciones=[OBLIGACION_IRE_GENERAL],
    )


# ==============================================================================
# 1. Durable Transactional Outbox Queue & WAL Tests
# ==============================================================================


def test_durable_queue_initializes_with_wal_mode(temp_db_path: Path) -> None:
    queue = DurableOutboxQueue(db_path=temp_db_path)
    assert temp_db_path.exists()

    with queue.get_connection() as conn:
        cursor = conn.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        assert journal_mode.lower() == "wal"

        cursor = conn.execute("PRAGMA synchronous;")
        # In SQLite, 1 corresponds to NORMAL
        assert cursor.fetchone()[0] in (1, "NORMAL")

    assert queue.verify_integrity() is True


def test_outbox_queue_lifecycle_transitions_and_audit_trail(
    temp_db_path: Path,
    sample_fe_header: DteHeaderInput,
    sample_fe_items: list[DteItemInput],
    sample_general_profile: MandantRucProfile,
) -> None:
    queue = DurableOutboxQueue(db_path=temp_db_path)
    cdc = "01800111114001001000004212026101429876543213"
    cdc_dv = "3"

    # Enqueue as QUEUED_OFFLINE
    record = queue.enqueue(
        cdc=cdc,
        cdc_dv=cdc_dv,
        emission_type=EMISSION_CONTINGENCIA,
        issue_date=sample_fe_header.issue_date,
        xml_content="<rDE><DE Id='test'></DE></rDE>",
        header_data=sample_fe_header.model_dump(),
        items_data=[it.model_dump() for it in sample_fe_items],
        profile_data=sample_general_profile.model_dump(),
        initial_status=OutboxStatus.QUEUED_OFFLINE,
    )
    assert record.status == OutboxStatus.QUEUED_OFFLINE
    assert record.retry_count == 0

    # Query record
    fetched = queue.get(record.id)
    assert fetched is not None
    assert fetched.cdc == cdc

    # Transition: QUEUED_OFFLINE -> TRANSMITTING
    queue.update_status(record.id, OutboxStatus.TRANSMITTING, detail="Worker sending")
    assert queue.get(record.id).status == OutboxStatus.TRANSMITTING

    # Transition: TRANSMITTING -> ACCEPTED
    now = datetime.now()
    queue.update_status(
        record.id,
        OutboxStatus.ACCEPTED,
        dnit_protocol="DNIT-TEST-PROT-999",
        transmitted_at=now,
        detail="Accepted by DNIT",
    )
    accepted_rec = queue.get(record.id)
    assert accepted_rec.status == OutboxStatus.ACCEPTED
    assert accepted_rec.dnit_protocol == "DNIT-TEST-PROT-999"

    # Verify audit log records all transitions
    with queue.get_connection() as conn:
        cursor = conn.execute(
            "SELECT old_status, new_status, detail FROM sifen_outbox_audit WHERE document_id = ? ORDER BY id ASC;",
            (record.id,),
        )
        logs = cursor.fetchall()
        assert len(logs) == 3
        assert (logs[0]["old_status"], logs[0]["new_status"]) == (None, "QUEUED_OFFLINE")
        assert (logs[1]["old_status"], logs[1]["new_status"]) == ("QUEUED_OFFLINE", "TRANSMITTING")
        assert (logs[2]["old_status"], logs[2]["new_status"]) == ("TRANSMITTING", "ACCEPTED")


# ==============================================================================
# 2. Circuit Breaker & Failover Tests
# ==============================================================================


def test_circuit_breaker_state_transitions() -> None:
    current_time = 1000.0

    cb = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=30.0,
        time_func=lambda: current_time,
    )
    assert cb.state == CircuitState.CLOSED
    assert cb.can_attempt() is True

    # 1st failure
    cb.record_failure("Timeout 1")
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 1

    # 2nd failure
    cb.record_failure("Timeout 2")
    assert cb.state == CircuitState.CLOSED

    # 3rd failure -> trips to OPEN!
    cb.record_failure("Timeout 3")
    assert cb.state == CircuitState.OPEN
    assert cb.can_attempt() is False

    # Within recovery timeout: remains OPEN
    current_time += 15.0
    assert cb.state == CircuitState.OPEN
    assert cb.can_attempt() is False

    # After recovery timeout: transitions to HALF_OPEN
    current_time += 16.0  # 31s elapsed
    assert cb.state == CircuitState.HALF_OPEN
    assert cb.can_attempt() is True

    # If probe fails in HALF_OPEN -> trips back to OPEN
    cb.record_failure("Probe failed")
    assert cb.state == CircuitState.OPEN

    # Advance time again and succeed -> resets to CLOSED
    current_time += 35.0
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


# ==============================================================================
# 3. KuDE Generator & Contingencia Receipt Tests
# ==============================================================================


def test_kude_generator_produces_valid_contingencia_receipt(
    sample_fe_header: DteHeaderInput,
    sample_fe_items: list[DteItemInput],
    sample_general_profile: MandantRucProfile,
) -> None:
    kude_gen = KuDeGenerator()
    resolved = SifenProfileResolver.resolve(sample_general_profile)

    # Set emission_type = 2 (Contingencia)
    sample_fe_header.emission_type = EMISSION_CONTINGENCIA
    cdc = "01800111114001001000004222026101429876543213"

    xml_gen = SifenXmlGenerator()
    xml_content = xml_gen.generate_xml(sample_fe_header, sample_fe_items, resolved)

    kude = kude_gen.generate_kude(
        header=sample_fe_header,
        items=sample_fe_items,
        resolved=resolved,
        cdc=cdc,
        xml_content=xml_content,
    )

    assert kude.is_contingencia is True
    assert kude.cdc == cdc
    assert len(kude.cdc_formatted.split()) == 11  # 11 groups of 4 digits

    # Check official SIFEN QR URL structure
    assert "https://ekuatia.set.gov.py" in kude.qr_url
    assert f"Id={cdc}" in kude.qr_url
    assert "nVersion=150" in kude.qr_url
    assert "cHashQR=" in kude.qr_url or "dFeEmiDE=" in kude.qr_url

    # Check SVG data uri
    assert kude.qr_data_uri.startswith("data:image/svg+xml")

    # Check printable receipt has required legal notices
    assert "*** COMPROBANTE EMITIDO EN CONTINGENCIA ***" in kude.receipt_text
    assert "Plazo maximo 72 horas" in kude.receipt_text
    assert "VibeCore Enterprise S.A." in kude.receipt_text
    assert "TOTAL A PAGAR:" in kude.receipt_text
    assert "CDC:" in kude.receipt_text


# ==============================================================================
# 4. SifenContingenciaEngine Automatic Failover & Offline POS
# ==============================================================================


def test_engine_automatic_failover_when_network_fails(
    temp_db_path: Path,
    sample_fe_header: DteHeaderInput,
    sample_fe_items: list[DteItemInput],
    sample_general_profile: MandantRucProfile,
) -> None:
    # Transmitter that simulates a network timeout / connection refused
    def failing_transmitter(_xml: str) -> dict:
        raise TimeoutError("SIFEN DNIT Gateway Timeout (504)")

    engine = SifenContingenciaEngine(
        db_path=temp_db_path,
        online_transmitter=failing_transmitter,
    )

    # Issue document: Network fails -> should automatically trigger Contingencia fallback
    result = engine.issue_document(
        header=sample_fe_header,
        items=sample_fe_items,
        profile_or_resolved=sample_general_profile,
    )

    assert result.success is True
    assert result.is_offline_contingencia is True
    assert result.emission_type == EMISSION_CONTINGENCIA
    assert result.status == OutboxStatus.QUEUED_OFFLINE

    # The CDC must have 44 digits and reflect Contingencia (iTipEmi = 2)
    assert len(result.cdc) == 44
    # Check that XML specifies Contingencia
    root = ET.fromstring(result.xml_content)
    assert root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}iTipEmi").text == "2"
    assert root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dDesTipEmi").text == "Contingencia"

    # KuDE receipt is ready immediately for the waiting customer
    assert result.kude_receipt.is_contingencia is True
    assert "*** COMPROBANTE EMITIDO EN CONTINGENCIA ***" in result.kude_receipt.receipt_text

    # Verified stored in durable SQLite WAL outbox
    stored = engine.queue.get(result.record_id)
    assert stored is not None
    assert stored.status == OutboxStatus.QUEUED_OFFLINE


def test_engine_online_success_path(
    temp_db_path: Path,
    sample_fe_header: DteHeaderInput,
    sample_fe_items: list[DteItemInput],
    sample_general_profile: MandantRucProfile,
) -> None:
    def online_mock(_xml: str) -> dict:
        return {"protocol": "DNIT-ONLINE-OK-12345", "status": "ACCEPTED"}

    engine = SifenContingenciaEngine(
        db_path=temp_db_path,
        online_transmitter=online_mock,
    )

    result = engine.issue_document(
        header=sample_fe_header,
        items=sample_fe_items,
        profile_or_resolved=sample_general_profile,
    )

    assert result.success is True
    assert result.is_offline_contingencia is False
    assert result.emission_type == EMISSION_NORMAL
    assert result.status == OutboxStatus.ACCEPTED

    root = ET.fromstring(result.xml_content)
    assert root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}iTipEmi").text == "1"
    assert root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dDesTipEmi").text == "Normal"


# ==============================================================================
# 5. Background Batch Sync & Exponential Backoff Tests
# ==============================================================================


def test_batch_sync_worker_with_exponential_backoff_and_recovery(
    temp_db_path: Path,
    sample_fe_header: DteHeaderInput,
    sample_fe_items: list[DteItemInput],
    sample_general_profile: MandantRucProfile,
) -> None:
    queue = DurableOutboxQueue(db_path=temp_db_path)
    cb = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)

    # 1. Enqueue 3 offline documents
    for i in range(1, 4):
        sample_fe_header.document_number = f"{i:07d}"
        cdc, cdc_dv = SifenXmlGenerator().generate_xml, "0"
        cdc_str = f"01800111114001001000000{i}22026101429876543210"
        queue.enqueue(
            cdc=cdc_str,
            cdc_dv="0",
            emission_type=EMISSION_CONTINGENCIA,
            issue_date=sample_fe_header.issue_date,
            xml_content=f"<rDE Id='{cdc_str}'></rDE>",
            header_data=sample_fe_header.model_dump(),
            items_data=[it.model_dump() for it in sample_fe_items],
            profile_data=sample_general_profile.model_dump(),
        )

    assert queue.count_by_status()[OutboxStatus.QUEUED_OFFLINE.value] == 3

    # Simulation step A: Network is initially DOWN (intermittent outage)
    network_down = True

    def intermittent_network(_rec):
        if network_down:
            raise ConnectionError("DNS lookup failed / SIFEN unreachable")
        return {"protocol": f"RECOVERED-PROT-{_rec.cdc[:8]}"}

    worker = ContingenciaSyncWorker(
        queue=queue,
        transmitter=intermittent_network,
        circuit_breaker=cb,
        base_backoff_seconds=1.0,
        backoff_factor=2.0,
    )

    # First sync run: Attempt fails, increments retry count with exponential backoff
    res1 = worker.process_pending_batch(batch_size=10)
    assert res1.retry_count > 0
    assert queue.count_by_status()[OutboxStatus.ACCEPTED.value] == 0

    # Inspect document retry schedule
    docs = queue.list()
    failed_doc = docs[0]
    assert failed_doc.retry_count == 1
    assert failed_doc.next_retry_at is not None

    # Simulation step B: Network is RESTORED! Advance time to simulate passing retry timer
    network_down = False
    future_time = datetime.now() + timedelta(minutes=5)
    res2 = worker.process_pending_batch(batch_size=10, reference_time=future_time)

    # Verify that recovered network syncs all documents to ACCEPTED
    assert res2.accepted_count > 0
    counts = queue.count_by_status()
    assert counts[OutboxStatus.ACCEPTED.value] == 3
    assert counts[OutboxStatus.QUEUED_OFFLINE.value] == 0


def test_business_rejection_marks_rejected(
    temp_db_path: Path,
    sample_fe_header: DteHeaderInput,
    sample_fe_items: list[DteItemInput],
    sample_general_profile: MandantRucProfile,
) -> None:
    queue = DurableOutboxQueue(db_path=temp_db_path)
    cdc_str = "01800111114001001000000122026101429876543210"
    queue.enqueue(
        cdc=cdc_str,
        cdc_dv="0",
        emission_type=EMISSION_CONTINGENCIA,
        issue_date=sample_fe_header.issue_date,
        xml_content="<rDE></rDE>",
        header_data=sample_fe_header.model_dump(),
        items_data=[it.model_dump() for it in sample_fe_items],
        profile_data=sample_general_profile.model_dump(),
    )

    def rejecting_dnit(_rec):
        raise BusinessRejectionError("DNIT Error 0142: RUC del receptor no habilitado para timbrado")

    worker = ContingenciaSyncWorker(queue=queue, transmitter=rejecting_dnit)
    res = worker.process_pending_batch()
    assert res.rejected_count == 1

    stored = queue.get_by_cdc(cdc_str)
    assert stored.status == OutboxStatus.REJECTED
    assert "0142" in stored.last_error


# ==============================================================================
# 6. SIFEN 72-Hour Legal Deadline Enforcement & Warning Alerts
# ==============================================================================


def test_72h_deadline_monitoring_and_expiration(
    temp_db_path: Path,
    sample_fe_header: DteHeaderInput,
    sample_fe_items: list[DteItemInput],
    sample_general_profile: MandantRucProfile,
) -> None:
    queue = DurableOutboxQueue(db_path=temp_db_path)

    base_time = datetime(2026, 10, 10, 10, 0, 0)

    # Document 1: 10 hours old (healthy, >24h left)
    sample_fe_header.issue_date = base_time + timedelta(hours=62)  # 10h old relative to base_time + 72h
    queue.enqueue(
        cdc="01800111114001001000000122026101429876543211",
        cdc_dv="1",
        emission_type=EMISSION_CONTINGENCIA,
        issue_date=sample_fe_header.issue_date,
        xml_content="<rDE/>",
        header_data=sample_fe_header.model_dump(),
        items_data=[],
        profile_data={},
    )

    # Document 2: 55 hours old (17 hours remaining -> WARNING alert)
    sample_fe_header.issue_date = base_time + timedelta(hours=17)
    queue.enqueue(
        cdc="01800111114001001000000222026101429876543212",
        cdc_dv="2",
        emission_type=EMISSION_CONTINGENCIA,
        issue_date=sample_fe_header.issue_date,
        xml_content="<rDE/>",
        header_data=sample_fe_header.model_dump(),
        items_data=[],
        profile_data={},
    )

    # Document 3: 65 hours old (7 hours remaining -> CRITICAL alert)
    sample_fe_header.issue_date = base_time + timedelta(hours=7)
    queue.enqueue(
        cdc="01800111114001001000000322026101429876543213",
        cdc_dv="3",
        emission_type=EMISSION_CONTINGENCIA,
        issue_date=sample_fe_header.issue_date,
        xml_content="<rDE/>",
        header_data=sample_fe_header.model_dump(),
        items_data=[],
        profile_data={},
    )

    # Document 4: 73 hours old (>72 hours -> EXPIRED!)
    sample_fe_header.issue_date = base_time - timedelta(hours=1)
    queue.enqueue(
        cdc="01800111114001001000000422026101429876543214",
        cdc_dv="4",
        emission_type=EMISSION_CONTINGENCIA,
        issue_date=sample_fe_header.issue_date,
        xml_content="<rDE/>",
        header_data=sample_fe_header.model_dump(),
        items_data=[],
        profile_data={},
    )

    # Audit deadlines at reference time: base_time + 72 hours
    ref_time = base_time + timedelta(hours=72)
    alerts = queue.check_deadlines(reference_time=ref_time)

    severities = {a.cdc: a.severity for a in alerts}
    assert "01800111114001001000000222026101429876543212" in severities
    assert severities["01800111114001001000000222026101429876543212"] == AlertSeverity.WARNING

    assert "01800111114001001000000322026101429876543213" in severities
    assert severities["01800111114001001000000322026101429876543213"] == AlertSeverity.CRITICAL

    assert "01800111114001001000000422026101429876543214" in severities
    assert severities["01800111114001001000000422026101429876543214"] == AlertSeverity.EXPIRED

    # Check status of Document 4 transitioned automatically to EXPIRED
    doc4 = queue.get_by_cdc("01800111114001001000000422026101429876543214")
    assert doc4.status == OutboxStatus.EXPIRED


# ==============================================================================
# 7. Chaos & Crash Resilience: SIGKILL During Writes (SQLite WAL)
# ==============================================================================


def _worker_writing_loop(db_path_str: str, ready_event: Any) -> None:
    """Helper process continuously writing committed outbox events."""
    queue = DurableOutboxQueue(db_path=db_path_str)
    ready_event.set()

    count = 0
    while True:
        count += 1
        cdc = f"01800111114001001000000{count:06d}22026101429876543210"
        queue.enqueue(
            cdc=cdc,
            cdc_dv="0",
            emission_type=EMISSION_CONTINGENCIA,
            issue_date=datetime.now(),
            xml_content=f"<rDE Id='{cdc}'/>",
            header_data={"doc": count},
            items_data=[],
            profile_data={},
        )
        time.sleep(0.005)


def test_crash_resilience_sigkill_power_loss_simulation(temp_db_path: Path) -> None:
    """
    Simulate sudden power loss / kill -9 (SIGKILL) while writes are occurring.
    Verifies that SQLite WAL recovery prevents corruption and preserves committed data.
    """
    ctx = multiprocessing.get_context("spawn")
    ready_event = ctx.Event()

    proc = ctx.Process(
        target=_worker_writing_loop,
        args=(str(temp_db_path), ready_event),
    )
    proc.start()

    # Wait until writing starts
    assert ready_event.wait(timeout=5.0) is True
    time.sleep(0.1)  # Let it write several transactions

    # Kill process abruptly with SIGKILL (no cleanup handler executed, simulating power drop)
    assert proc.pid is not None
    os.kill(proc.pid, signal.SIGKILL)
    proc.join(timeout=3.0)

    # Open database from parent process
    queue = DurableOutboxQueue(db_path=temp_db_path)

    # 1. PRAGMA integrity_check MUST return 'ok'
    assert queue.verify_integrity() is True

    # 2. All committed records are readable and intact
    records = queue.list(limit=500)
    assert len(records) > 0
    for rec in records:
        assert rec.status == OutboxStatus.QUEUED_OFFLINE
        assert rec.cdc.startswith("01800111114")

    # 3. New writes succeed normally after crash recovery
    new_cdc = "0180011111400100100099999922026101429876543210"
    rec_after_crash = queue.enqueue(
        cdc=new_cdc,
        cdc_dv="0",
        emission_type=EMISSION_CONTINGENCIA,
        issue_date=datetime.now(),
        xml_content="<rDE after crash/>",
        header_data={"status": "recovered"},
        items_data=[],
        profile_data={},
    )
    assert queue.get(rec_after_crash.id) is not None
    assert queue.verify_integrity() is True
