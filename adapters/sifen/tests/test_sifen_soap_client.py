"""
Unit tests for SIFEN SOAP 1.2 and mTLS client.
"""

from unittest.mock import MagicMock, patch

from sifen.client import (
    SifenSoapClient,
    build_soap12_envelope,
    clean_xml_for_soap_envelope,
    parse_sifen_soap_response,
)
from sifen.signer import generate_mock_pkcs12


def test_clean_xml_and_soap_envelope_construction() -> None:
    raw = '<?xml version="1.0" encoding="utf-8"?>\n<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"><DE Id="123"/></rDE>'
    cleaned = clean_xml_for_soap_envelope(raw)
    assert not cleaned.startswith("<?xml")
    assert cleaned.startswith("<rDE")

    envelope = build_soap12_envelope(raw, doc_id="1001")
    assert "<soap12:Envelope" in envelope
    assert "<sifen:dId>1001</sifen:dId>" in envelope
    assert "<sifen:xDE>" in envelope
    assert "<DE Id=\"123\"/>" in envelope


def test_parse_sifen_soap_response_approved() -> None:
    resp_xml = """<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope" xmlns:sifen="http://ekuatia.set.gov.py/sifen/xsd">
      <soap12:Body>
        <sifen:rRetEnviDe>
          <sifen:dFecProc>2026-10-14T18:40:00Z</sifen:dFecProc>
          <sifen:rProtDe>
            <sifen:Id>01800111114001001000000222026101411234567894</sifen:Id>
            <sifen:gResProc>
              <sifen:dCodRes>0260</sifen:dCodRes>
              <sifen:dMsgRes>Aprobado</sifen:dMsgRes>
            </sifen:gResProc>
          </sifen:rProtDe>
        </sifen:rRetEnviDe>
      </soap12:Body>
    </soap12:Envelope>"""

    success, status, cod, msg, fec = parse_sifen_soap_response(resp_xml)
    assert success is True
    assert status == "Aprobado"
    assert cod == "0260"
    assert msg == "Aprobado"
    assert fec == "2026-10-14T18:40:00Z"


def test_parse_sifen_soap_response_rejected() -> None:
    resp_xml = """<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope" xmlns="http://ekuatia.set.gov.py/sifen/xsd">
      <soap12:Body>
        <rRetEnviDe>
          <dFecProc>2026-10-14T18:40:00Z</dFecProc>
          <rProtDe>
            <gResProc>
              <dCodRes>0160</dCodRes>
              <dMsgRes>XML malformado o firma invalida</dMsgRes>
            </gResProc>
          </rProtDe>
        </rRetEnviDe>
      </soap12:Body>
    </soap12:Envelope>"""

    success, status, cod, msg, _ = parse_sifen_soap_response(resp_xml)
    assert success is False
    assert status == "Rechazado"
    assert cod == "0160"
    assert "XML malformado" in msg


def test_soap_client_simulation_mode() -> None:
    client = SifenSoapClient(simulation=True)
    res = client.send_document(
        signed_xml="<rDE>test</rDE>",
        cdc="01800111114001001000000222026101411234567894",
        qr_url="https://ekuatia.set.gov.py/consultas-test/qr?Id=01800111114",
    )
    assert res.success is True
    assert res.status == "Aprobado"
    assert res.dCodRes == "0260"
    assert res.cdc == "01800111114001001000000222026101411234567894"
    assert "Aprobado" in res.raw_response


def test_soap_client_with_mocked_http() -> None:
    p12_bytes, pwd = generate_mock_pkcs12()
    client = SifenSoapClient(p12_bytes=p12_bytes, password=pwd, simulation=False)

    fake_response = MagicMock()
    fake_response.text = """<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope" xmlns:sifen="http://ekuatia.set.gov.py/sifen/xsd">
      <soap12:Body>
        <sifen:rRetEnviDe>
          <sifen:dFecProc>2026-10-14T18:50:00Z</sifen:dFecProc>
          <sifen:rProtDe>
            <sifen:gResProc>
              <sifen:dCodRes>0500</sifen:dCodRes>
              <sifen:dMsgRes>Aprobado con advertencia de timbrado</sifen:dMsgRes>
            </sifen:gResProc>
          </sifen:rProtDe>
        </sifen:rRetEnviDe>
      </soap12:Body>
    </soap12:Envelope>"""

    with patch("httpx.Client.post", return_value=fake_response) as mock_post:
        res = client.send_document(
            signed_xml="<rDE><DE Id=\"test\"/></rDE>",
            cdc="01800111114001001000000222026101411234567894",
            qr_url="https://ekuatia.set.gov.py/consultas-test/qr?test",
        )
        assert mock_post.called
        assert res.success is True
        assert res.dCodRes == "0500"
        assert res.status == "Aprobado"
