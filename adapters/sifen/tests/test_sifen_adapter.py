"""
Comprehensive test suite for the isolated SIFEN Fiscal Adapter microservice.
Covers:
1. Semantic XML payload verification (Factura Electrónica iTiDE=1 & Boleta Resimple iTiDE=4, Modulo-11 44-digit CDC, Ley 6380/19 IVA).
2. Persistent Outbox Queue resilience under network timeouts and upstream 5xx outages, plus FIFO recovery flush.
3. Idempotency, authentication, and observability endpoints (/health, /ready).
"""

import xml.etree.ElementTree as ET
from collections.abc import Generator
from datetime import datetime
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sifen.client import SifenClient
from sifen.config import Settings
from sifen.constants import (
    DTE_BOLETA_RESIMPLE,
    DTE_FACTURA_ELECTRONICA,
    OBLIGACION_IRE_GENERAL,
    OBLIGACION_IRE_RESIMPLE,
    OBLIGACION_IRE_SIMPLE,
    TaxRegime,
)
from sifen.database import get_db
from sifen.db_models import Base, SifenOutboxRecord
from sifen.main import create_app
from sifen.models import (
    DteHeaderInput,
    DteItemInput,
    MandantRucProfile,
    OutboxStatus,
)
from sifen.resolver import SifenProfileResolver
from sifen.service import SifenService
from sifen.xml_generator import SifenXmlGenerator, generate_sifen_cdc
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

SIFEN_APPROVED_SOAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
  <env:Body>
    <ns2:rRetEnviDe xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
      <ns2:rProtDe>
        <ns2:Id>01800111114001001000000222026101411234567896</ns2:Id>
        <ns2:dFecProc>2026-10-14T12:00:05-03:00</ns2:dFecProc>
        <ns2:dEstRes>Aprobado</ns2:dEstRes>
        <ns2:dProtAut>9988776655</ns2:dProtAut>
        <ns2:gResProc>
          <ns2:dCodRes>0260</ns2:dCodRes>
          <ns2:dMsgRes>Aprobamiento satisfactorio del DE</ns2:dMsgRes>
        </ns2:gResProc>
      </ns2:rProtDe>
    </ns2:rRetEnviDe>
  </env:Body>
</env:Envelope>"""

SIFEN_REJECTED_SOAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
  <env:Body>
    <ns2:rRetEnviDe xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
      <ns2:rProtDe>
        <ns2:dEstRes>Rechazado</ns2:dEstRes>
        <ns2:gResProc>
          <ns2:dCodRes>0160</ns2:dCodRes>
          <ns2:dMsgRes>XML mal formado o firma invalida</ns2:dMsgRes>
        </ns2:gResProc>
      </ns2:rProtDe>
    </ns2:rRetEnviDe>
  </env:Body>
</env:Envelope>"""


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        sifen_env="sandbox",
        sifen_base_url="https://sifen-test.set.gov.py",
        database_url="sqlite:///:memory:",
        request_timeout_seconds=2.0,
        max_retries=2,
    )


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_client(db_engine, test_settings) -> Generator[TestClient, None, None]:
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    import sifen.router as router_module

    router_module.settings = test_settings
    router_module.service = SifenService(
        client=SifenClient(test_settings),
        custom_settings=test_settings,
    )

    with TestClient(app) as client:
        yield client


def _sample_submit_payload(doc_number: str = "0000002", obligacion: int = OBLIGACION_IRE_GENERAL) -> dict:
    return {
        "header": {
            "timbrado_number": "87654321",
            "establishment_code": "001",
            "point_of_issue_code": "001",
            "document_number": doc_number,
            "issue_date": "2026-10-14T12:00:00",
            "security_code": "123456789",
            "issuer_ruc": "80011111",
            "issuer_dv": "4",
            "issuer_legal_name": "Comercio Grande S.A.",
            "currency": "PYG",
        },
        "items": [
            {
                "line_number": 1,
                "description": "Servidor VibeCore Enterprise",
                "quantity": "1",
                "unit_price": "11000000",
                "tax_rate": "10",
            },
            {
                "line_number": 2,
                "description": "Canasta Basica Familiar",
                "quantity": "1",
                "unit_price": "10000",
                "tax_rate": "5",
            },
        ],
        "profile": {
            "ruc": "80011111",
            "dv": "4",
            "legal_name": "Comercio Grande S.A.",
            "obligaciones": [obligacion],
        },
        "meta": {"source": "vibecore-core"},
        "custom_data": {"branch": "ASU-01"},
    }


def test_adapter_resolver_and_generator_workflow() -> None:
    # 1. Test IRE Resimple (702) -> Boleta Resimple (iTiDE = 4)
    resimple_profile = MandantRucProfile(
        ruc="80076543",
        dv="2",
        legal_name="Comercio Pequeno de Juan",
        obligaciones=[OBLIGACION_IRE_RESIMPLE],
    )
    resolved_resimple = SifenProfileResolver.resolve(resimple_profile)
    assert resolved_resimple.regime == TaxRegime.IRE_RESIMPLE
    assert resolved_resimple.dte_type == DTE_BOLETA_RESIMPLE
    assert resolved_resimple.iva_applicable is False

    header = DteHeaderInput(
        timbrado_number="87654321",
        establishment_code="001",
        point_of_issue_code="001",
        document_number="0000001",
        issue_date=datetime(2026, 10, 14, 12, 0, 0),
        security_code="123456789",
        issuer_ruc="80076543",
        issuer_dv="2",
        issuer_legal_name="Comercio Pequeno de Juan",
        currency="PYG",
    )
    items = [
        DteItemInput(
            line_number=1,
            description="Venta de Verduras Frescas",
            quantity=Decimal(5),
            unit_price=Decimal(10000),
            tax_rate=Decimal(10),
        )
    ]

    generator = SifenXmlGenerator()
    xml_resimple = generator.generate_xml(header, items, resolved_resimple)
    root = ET.fromstring(xml_resimple)
    assert root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}iTiDE").text == "4"
    assert root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}iAfecIVA").text == "3"
    assert root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dTotIVA").text == "0"
    assert root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dTotOpe").text == "50000"

    # 2. Test IRE General (700) & Simple (701) -> Factura Electrónica (iTiDE = 1) with exact Ley 6380/19 IVA balance
    general_profile = MandantRucProfile(
        ruc="80011111",
        dv="4",
        legal_name="Comercio Grande S.A.",
        obligaciones=[OBLIGACION_IRE_GENERAL],
    )
    resolved_general = SifenProfileResolver.resolve(general_profile)
    assert resolved_general.regime == TaxRegime.IRE_GENERAL
    assert resolved_general.dte_type == DTE_FACTURA_ELECTRONICA
    assert resolved_general.iva_applicable is True

    simple_resolved = SifenProfileResolver.resolve([OBLIGACION_IRE_SIMPLE])
    assert simple_resolved.regime == TaxRegime.IRE_SIMPLE
    assert simple_resolved.dte_type == DTE_FACTURA_ELECTRONICA

    header_fe = DteHeaderInput(
        timbrado_number="87654321",
        establishment_code="001",
        point_of_issue_code="001",
        document_number="0000002",
        issue_date=datetime(2026, 10, 14, 12, 0, 0),
        security_code="123456789",
        issuer_ruc="80011111",
        issuer_dv="4",
        issuer_legal_name="Comercio Grande S.A.",
        currency="PYG",
    )
    items_fe = [
        DteItemInput(
            line_number=1,
            description="Servidor VibeCore Enterprise",
            quantity=Decimal(1),
            unit_price=Decimal(10000),  # Non-divisible by 11 to test exact PYG rounding balance
            tax_rate=Decimal(10),
        ),
        DteItemInput(
            line_number=2,
            description="Insumo Agricola Gravado 5%",
            quantity=Decimal(1),
            unit_price=Decimal(10000),  # Non-divisible by 21 to test exact PYG rounding balance
            tax_rate=Decimal(5),
        ),
    ]
    xml_fe = generator.generate_xml(header_fe, items_fe, resolved_general)
    root_fe = ET.fromstring(xml_fe)
    ns = "{http://ekuatia.set.gov.py/sifen/xsd}"
    assert root_fe.find(f".//{ns}iTiDE").text == "1"

    # Verify 10% item: 10000 / 11 = 909 IVA, 9091 Base (9091 + 909 == 10000)
    assert root_fe.find(f".//{ns}dIVA10").text == "909"
    assert root_fe.find(f".//{ns}dBaseGrav10").text == "9091"

    # Verify 5% item: 10000 / 21 = 476 IVA, 9524 Base (9524 + 476 == 10000)
    assert root_fe.find(f".//{ns}dIVA5").text == "476"
    assert root_fe.find(f".//{ns}dBaseGrav5").text == "9524"

    # Total IVA = 909 + 476 = 1385, Total Base = 9091 + 9524 = 18615, Sum = 20000 == dTotGralOpe
    assert root_fe.find(f".//{ns}dTotIVA").text == "1385"
    assert root_fe.find(f".//{ns}dTotBasGrav").text == "18615"
    assert root_fe.find(f".//{ns}dTotGralOpe").text == "20000"

    cdc, dv = generate_sifen_cdc(header_fe, DTE_FACTURA_ELECTRONICA)
    assert len(cdc) == 44
    assert cdc.endswith(dv)


def test_health_and_ready_endpoints(test_client: TestClient) -> None:
    resp_health = test_client.get("/health")
    assert resp_health.status_code == 200
    assert resp_health.json()["status"] == "healthy"
    assert resp_health.json()["service"] == "sifen-adapter"

    resp_ready = test_client.get("/ready")
    assert resp_ready.status_code == 200
    assert resp_ready.json()["ready"] is True
    assert resp_ready.json()["database"] == "connected"


def test_resolve_and_generate_xml_endpoints(test_client: TestClient) -> None:
    resolve_resp = test_client.post(
        "/api/v1/sifen/resolve",
        json={
            "ruc": "80011111",
            "dv": "4",
            "legal_name": "Comercio Grande S.A.",
            "obligaciones": [700],
        },
    )
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["dte_type"] == 1
    assert resolve_resp.json()["dte_type_code"] == "01"

    invalid_resp = test_client.post(
        "/api/v1/sifen/resolve",
        json={
            "ruc": "80011111",
            "dv": "4",
            "legal_name": "Invalid S.A.",
            "obligaciones": [999],
        },
    )
    assert invalid_resp.status_code == 400

    xml_resp = test_client.post(
        "/api/v1/sifen/generate-xml",
        json=_sample_submit_payload(),
    )
    assert xml_resp.status_code == 200
    assert "application/xml" in xml_resp.headers["content-type"]
    root = ET.fromstring(xml_resp.text)
    assert root.find(".//{http://ekuatia.set.gov.py/sifen/xsd}dTotGralOpe").text == "11010000"


def test_submit_dte_live_soap_approval_and_idempotency(
    monkeypatch, test_client: TestClient
) -> None:
    call_count = 0

    async def mock_post(client_self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        assert "/de/ws/sync/recibe.wsdl" in str(url)
        soap_payload = kwargs.get("content", b"").decode("utf-8")
        assert "<rEnviDe" in soap_payload
        assert "<rDE" in soap_payload
        return httpx.Response(status_code=200, text=SIFEN_APPROVED_SOAP_XML)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    payload = _sample_submit_payload(doc_number="0000010")
    resp1 = test_client.post(
        "/api/v1/sifen/submit",
        json=payload,
        headers={"X-Idempotency-Key": "sifen-idem-010"},
    )
    assert resp1.status_code == 201
    data1 = resp1.json()
    assert data1["status"] == OutboxStatus.ACCEPTED.value
    assert data1["sifen_code"] == "0260"
    assert data1["protocol_number"] == "9988776655"
    assert data1["meta"] == {"source": "vibecore-core"}
    assert data1["custom_data"] == {"branch": "ASU-01"}
    assert call_count == 1

    # Duplicate submission with same idempotency key does NOT re-transmit to SIFEN
    resp2 = test_client.post(
        "/api/v1/sifen/submit",
        json=payload,
        headers={"X-Idempotency-Key": "sifen-idem-010"},
    )
    assert resp2.status_code == 201
    assert resp2.json()["cdc"] == data1["cdc"]
    assert call_count == 1


def test_persistent_outbox_queue_on_network_outage_and_recovery_flush(
    monkeypatch, test_client: TestClient, db_session: Session
) -> None:
    network_down = True

    async def mock_post(client_self, url, **kwargs):
        if network_down:
            raise httpx.ConnectTimeout("Connection timed out to sifen-test.set.gov.py")
        return httpx.Response(status_code=200, text=SIFEN_APPROVED_SOAP_XML)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    # 1. Submit while SIFEN is unreachable -> DTE is stored in persistent Outbox as QUEUED
    payload = _sample_submit_payload(doc_number="0000025")
    submit_resp = test_client.post("/api/v1/sifen/submit", json=payload)
    assert submit_resp.status_code == 201
    queued_data = submit_resp.json()
    cdc = queued_data["cdc"]
    assert queued_data["status"] == OutboxStatus.QUEUED.value
    assert queued_data["retry_count"] == 1
    assert "unreachable" in (queued_data["last_error"] or "")

    # Verify record is persisted in SQLite Outbox
    record = db_session.query(SifenOutboxRecord).filter_by(cdc=cdc).first()
    assert record is not None
    assert record.status == OutboxStatus.QUEUED.value

    # List QUEUED items via API
    list_resp = test_client.get("/api/v1/sifen/outbox?status=QUEUED")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["cdc"] == cdc

    # 2. Flush while network is still down -> stays QUEUED, retry_count increments to 2
    flush_down_resp = test_client.post("/api/v1/sifen/outbox/flush")
    assert flush_down_resp.status_code == 200
    assert flush_down_resp.json()["processed_count"] == 1
    assert flush_down_resp.json()["still_queued_count"] == 1
    assert flush_down_resp.json()["items"][0]["retry_count"] == 2

    # 3. Network recovers -> Flush transmits queued DTE and marks it ACCEPTED
    network_down = False
    flush_up_resp = test_client.post("/api/v1/sifen/outbox/flush")
    assert flush_up_resp.status_code == 200
    flush_data = flush_up_resp.json()
    assert flush_data["processed_count"] == 1
    assert flush_data["accepted_count"] == 1
    assert flush_data["still_queued_count"] == 0
    assert flush_data["items"][0]["status"] == OutboxStatus.ACCEPTED.value
    assert flush_data["items"][0]["sifen_code"] == "0260"

    # Verify GET by CDC returns ACCEPTED
    get_resp = test_client.get(f"/api/v1/sifen/outbox/{cdc}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == OutboxStatus.ACCEPTED.value
    assert get_resp.json()["last_error"] is None


def test_submit_dte_business_rejection_from_sifen(
    monkeypatch, test_client: TestClient
) -> None:
    async def mock_post(client_self, url, **kwargs):
        return httpx.Response(status_code=200, text=SIFEN_REJECTED_SOAP_XML)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    payload = _sample_submit_payload(doc_number="0000099")
    resp = test_client.post("/api/v1/sifen/submit", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == OutboxStatus.REJECTED.value
    assert data["sifen_code"] == "0160"
    assert "firma invalida" in data["sifen_message"]
