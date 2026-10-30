"""
FastAPI route definitions for the SIFEN Fiscal Adapter.
Exposes REST endpoints for RUC profile resolution, DTE XML generation,
and resilient DTE submission backed by a persistent Outbox Queue.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from sifen.client import SifenNotFoundError
from sifen.config import settings
from sifen.database import get_db
from sifen.models import (
    DteOutboxResponse,
    GenerateXmlRequest,
    MandantRucProfile,
    OutboxFlushResponse,
    ResolvedProfile,
    SubmitDteRequest,
)
from sifen.resolver import SifenProfileResolver
from sifen.service import SifenService
from sifen.xml_generator import SifenXmlGenerator

router = APIRouter(prefix="/api/v1/sifen", tags=["SIFEN Electronic Invoicing"])
service = SifenService()
generator = SifenXmlGenerator()


def verify_adapter_auth(
    x_adapter_key: str | None = Header(None, alias="X-Adapter-Key"),
    authorization: str | None = Header(None),
) -> None:
    """Verifies internal adapter authentication if ADAPTER_API_KEY is configured."""
    if not settings.adapter_api_key:
        return

    expected = settings.adapter_api_key
    if x_adapter_key == expected:
        return

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
        if token == expected:
            return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized adapter request. Invalid or missing API key.",
    )


@router.post(
    "/resolve",
    response_model=ResolvedProfile,
    status_code=status.HTTP_200_OK,
    summary="Resolve Mandant RUC profile into DTE type and tax calculation policy",
)
def resolve_ruc_profile(
    profile: MandantRucProfile,
    _auth: None = Depends(verify_adapter_auth),
) -> ResolvedProfile:
    try:
        return SifenProfileResolver.resolve(profile)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.post(
    "/generate-xml",
    status_code=status.HTTP_200_OK,
    summary="Generate official SIFEN XML for Factura Electrónica or Boleta Resimple Electrónica",
)
def generate_sifen_xml(
    request: GenerateXmlRequest,
    _auth: None = Depends(verify_adapter_auth),
) -> Response:
    try:
        xml_doc = generator.generate_xml(
            header=request.header,
            items=request.items,
            profile_or_resolved=request.profile,
            pretty=True,
        )
        return Response(
            content=xml_doc,
            media_type="application/xml",
            status_code=status.HTTP_200_OK,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.post(
    "/submit",
    response_model=DteOutboxResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate and submit DTE to SIFEN with persistent Outbox Queue fallback on network outage",
)
async def submit_dte(
    request: SubmitDteRequest,
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_adapter_auth),
) -> DteOutboxResponse:
    try:
        return await service.submit_dte(
            db=db,
            request=request,
            idempotency_key=x_idempotency_key,
            correlation_id=x_correlation_id,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.post(
    "/outbox/flush",
    response_model=OutboxFlushResponse,
    status_code=status.HTTP_200_OK,
    summary="Retry all QUEUED DTEs from the persistent Outbox Queue",
)
async def flush_outbox(
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_adapter_auth),
) -> OutboxFlushResponse:
    return await service.flush_outbox(db=db, correlation_id=x_correlation_id)


@router.get(
    "/outbox",
    response_model=list[DteOutboxResponse],
    status_code=status.HTTP_200_OK,
    summary="List DTE records in the persistent Outbox Queue",
)
def list_outbox_records(
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_adapter_auth),
) -> list[DteOutboxResponse]:
    return service.list_outbox(db=db, status_filter=status_filter)


@router.get(
    "/outbox/{cdc}",
    response_model=DteOutboxResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve DTE submission and Outbox status by 44-digit CDC",
)
def get_outbox_record(
    cdc: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(verify_adapter_auth),
) -> DteOutboxResponse:
    try:
        return service.get_by_cdc(db=db, cdc=cdc)
    except SifenNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
