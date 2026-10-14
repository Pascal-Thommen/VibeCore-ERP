"""
FastAPI application server for VibeCore SIFEN Adapter Microservice.
"""

from __future__ import annotations

import base64
from typing import Any

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware

from sifen.client import SifenSoapClient
from sifen.models import (
    GenerateXmlRequest,
    MandantRucProfile,
    ResolvedProfile,
    SignAndSendRequest,
    SignAndSendResponse,
    SignRequest,
    SignResponse,
)
from sifen.resolver import SifenProfileResolver
from sifen.signer import SifenSigner
from sifen.xml_generator import SifenXmlGenerator

app = FastAPI(
    title="VibeCore SIFEN Adapter API",
    version="1.0.0",
    description="Isolated adapter service for Paraguayan SIFEN electronic invoicing and dynamic DTE resolution.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

profile_resolver = SifenProfileResolver()
xml_generator = SifenXmlGenerator(resolver=profile_resolver)


@app.get("/health", tags=["Health"])
@app.get("/api/v1/sifen/health", tags=["Health"])
def health_check() -> dict[str, str]:
    """Microservice health check endpoint."""
    return {
        "status": "healthy",
        "service": "sifen-adapter",
        "version": "1.0.0",
    }


@app.post(
    "/api/v1/sifen/resolve",
    response_model=ResolvedProfile,
    summary="Resolve Mandant RUC profile into DTE type and tax calculation policy",
    tags=["SIFEN"],
)
def resolve_profile(profile: MandantRucProfile) -> ResolvedProfile:
    """Resolve taxpayer RUC profile into official DTE type and IVA regime."""
    try:
        return profile_resolver.resolve(profile)
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/v1/sifen/generate-xml",
    summary="Generate official SIFEN XML for Factura Electrónica or Boleta Resimple Electrónica",
    tags=["SIFEN"],
    responses={
        200: {
            "content": {"application/xml": {"schema": {"type": "string"}}},
            "description": "Generated XML document",
        },
        400: {"description": "Validation or calculation error"},
    },
)
def generate_xml(req: GenerateXmlRequest) -> Response:
    """Generate compliant SIFEN v150 XML according to taxpayer regime."""
    try:
        xml_content = xml_generator.generate_xml(
            header=req.header,
            items=req.items,
            profile_or_resolved=req.profile,
            pretty=True,
        )
        return Response(content=xml_content, media_type="application/xml")
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/v1/sifen/sign",
    response_model=SignResponse,
    summary="Sign SIFEN XML with XMLDSig and generate official KuDE QR code",
    tags=["SIFEN"],
)
def sign_xml(req: SignRequest) -> SignResponse:
    """Digitally sign XML document with PKCS#12 certificate and attach QR code."""
    try:
        raw_xml = req.raw_xml
        if not raw_xml:
            if not req.header or not req.items or not req.profile:
                raise ValueError(
                    "Either 'raw_xml' or ('header', 'items', 'profile') must be provided."
                )
            raw_xml = xml_generator.generate_xml(
                header=req.header,
                items=req.items,
                profile_or_resolved=req.profile,
            )

        p12_bytes = base64.b64decode(req.cert_p12_base64) if req.cert_p12_base64 else None
        signer = SifenSigner(
            p12_bytes=p12_bytes,
            p12_path=req.cert_path,
            password=req.cert_password,
            allow_mock=True,
        )

        signed_xml, qr_url, cdc, digest_value = signer.sign_and_add_qr(
            raw_xml=raw_xml,
            csc=req.csc,
            id_csc=req.id_csc,
            ambiente=req.ambiente,
            header=req.header,
        )

        return SignResponse(
            success=True,
            cdc=cdc,
            xml_signed=signed_xml,
            qr_url=qr_url,
            digest_value=digest_value,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@app.post(
    "/api/v1/sifen/sign-and-send",
    response_model=SignAndSendResponse,
    summary="Sign XML with XMLDSig, generate QR, and transmit to DNIT e-Kuatia via SOAP 1.2 / mTLS",
    tags=["SIFEN"],
)
def sign_and_send(req: SignAndSendRequest) -> SignAndSendResponse:
    """Sign DTE and transmit to DNIT e-Kuatia SOAP webservice."""
    try:
        raw_xml = req.raw_xml
        if not raw_xml:
            if not req.header or not req.items or not req.profile:
                raise ValueError(
                    "Either 'raw_xml' or ('header', 'items', 'profile') must be provided."
                )
            raw_xml = xml_generator.generate_xml(
                header=req.header,
                items=req.items,
                profile_or_resolved=req.profile,
            )

        p12_bytes = base64.b64decode(req.cert_p12_base64) if req.cert_p12_base64 else None
        signer = SifenSigner(
            p12_bytes=p12_bytes,
            p12_path=req.cert_path,
            password=req.cert_password,
            allow_mock=True,
        )

        signed_xml, qr_url, cdc, _ = signer.sign_and_add_qr(
            raw_xml=raw_xml,
            csc=req.csc,
            id_csc=req.id_csc,
            ambiente=req.ambiente,
            header=req.header,
        )

        soap_client = SifenSoapClient(
            endpoint_url=req.endpoint_url,
            p12_bytes=signer.p12_bytes,
            password=signer.password,
            simulation=req.simulation,
        )

        return soap_client.send_document(
            signed_xml=signed_xml,
            cdc=cdc,
            qr_url=qr_url,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
