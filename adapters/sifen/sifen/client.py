"""
SOAP 1.2 HTTP Client for SIFEN (DNIT / SET Paraguay) DTE Transmission.
Builds official rEnviDe envelopes, enforces explicit network timeouts,
and parses real SIFEN rRetEnviDe XML responses.
"""

import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from sifen.config import Settings, settings
from sifen.constants import SIFEN_XML_NAMESPACE

logger = logging.getLogger("sifen.client")

SOAP_ENV_NS = "http://www.w3.org/2003/05/soap-envelope"
APPROVED_CODES = {"0260", "1005"}


class SifenError(Exception):
    """Base exception for SIFEN adapter operations."""


class SifenNetworkError(SifenError):
    """Raised when SIFEN network transmission times out or encounters upstream 5xx errors."""


class SifenNotFoundError(SifenError):
    """Raised when a requested DTE record is not found in the local outbox."""


class SifenClient:
    """Client for synchronous DTE transmission to SIFEN (/de/ws/sync/recibe.wsdl)."""

    def __init__(self, custom_settings: Settings | None = None) -> None:
        self.cfg = custom_settings or settings

    @staticmethod
    def build_soap_envelope(cdc: str, dte_xml: str, request_id: int = 1) -> str:
        """
        Wraps a generated SIFEN <rDE> XML document inside an official SOAP 1.2 <rEnviDe> envelope.
        """
        clean_xml = dte_xml.strip()
        if clean_xml.startswith("<?xml"):
            clean_xml = clean_xml.split("?>", 1)[-1].strip()

        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<env:Envelope xmlns:env="{SOAP_ENV_NS}">\n'
            "  <env:Header/>\n"
            "  <env:Body>\n"
            f'    <rEnviDe xmlns="{SIFEN_XML_NAMESPACE}">\n'
            f"      <dId>{request_id}</dId>\n"
            f"      <xDE>{clean_xml}</xDE>\n"
            "    </rEnviDe>\n"
            "  </env:Body>\n"
            "</env:Envelope>"
        )

    @staticmethod
    def parse_soap_response(raw_xml: str) -> dict[str, Any]:
        """
        Parses SIFEN SOAP XML response (rRetEnviDe / rProtDe / gResProc).
        Extracts dCodRes, dMsgRes, dEstRes, and dProtAut regardless of namespace prefixes.
        """
        try:
            root = ET.fromstring(raw_xml.encode("utf-8"))
        except ET.ParseError as exc:
            raise SifenNetworkError(f"Malformed XML response from SIFEN: {exc}") from exc

        fields: dict[str, str] = {}
        for elem in root.iter():
            local_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if elem.text and elem.text.strip() and local_name not in fields:
                fields[local_name] = elem.text.strip()

        code = fields.get("dCodRes", "")
        message = fields.get("dMsgRes", "")
        estado = fields.get("dEstRes", "")
        protocol = fields.get("dProtAut")

        if not code and not estado:
            fault_reason = fields.get("Text") or fields.get("faultstring")
            if fault_reason:
                raise SifenNetworkError(f"SIFEN SOAP Fault: {fault_reason}")
            raise SifenNetworkError("SIFEN response missing dCodRes and dEstRes")

        is_accepted = (code in APPROVED_CODES) or (estado.lower().startswith("aprobado"))
        return {
            "accepted": is_accepted,
            "sifen_code": code or ("0260" if is_accepted else "0160"),
            "sifen_message": message or estado or "Processed by SIFEN",
            "protocol_number": protocol,
        }

    async def transmit_dte(
        self,
        cdc: str,
        dte_xml: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Transmits a DTE SOAP envelope to SIFEN with explicit timeouts and retries.
        Raises SifenNetworkError on network outage or HTTP 5xx so the caller keeps the DTE in the Outbox.
        """
        url = f"{self.cfg.resolved_base_url}/de/ws/sync/recibe.wsdl"
        soap_body = self.build_soap_envelope(cdc=cdc, dte_xml=dte_xml)
        headers = {
            "Content-Type": "application/soap+xml; charset=utf-8",
            "Accept": "application/soap+xml, text/xml, application/xml",
        }
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        last_error: Exception | None = None
        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.cfg.request_timeout_seconds
                ) as client:
                    logger.info(
                        "Transmitting DTE cdc=%s to %s (attempt %d/%d)",
                        cdc,
                        url,
                        attempt,
                        self.cfg.max_retries,
                    )
                    resp = await client.post(
                        url,
                        content=soap_body.encode("utf-8"),
                        headers=headers,
                    )

                if resp.status_code >= 500:
                    logger.warning(
                        "SIFEN server error status=%d body=%s",
                        resp.status_code,
                        resp.text,
                    )
                    if attempt < self.cfg.max_retries:
                        await asyncio.sleep(0.1 * (2 ** (attempt - 1)))
                        continue
                    raise SifenNetworkError(
                        f"SIFEN upstream HTTP {resp.status_code}: {resp.text}"
                    )

                if resp.status_code >= 400:
                    raise SifenNetworkError(
                        f"SIFEN HTTP rejection ({resp.status_code}): {resp.text}"
                    )

                return self.parse_soap_response(resp.text)

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                logger.warning(
                    "Network outage calling SIFEN for cdc=%s (attempt %d/%d): %s",
                    cdc,
                    attempt,
                    self.cfg.max_retries,
                    exc,
                )
                last_error = exc
                if attempt < self.cfg.max_retries:
                    await asyncio.sleep(0.1 * (2 ** (attempt - 1)))
                    continue
                raise SifenNetworkError(
                    f"SIFEN unreachable after {self.cfg.max_retries} attempts: {exc}"
                ) from exc

        raise SifenNetworkError(f"SIFEN transmission failed: {last_error}")
