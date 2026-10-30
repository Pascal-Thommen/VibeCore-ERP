"""Minimal, typed HTTP client boundary for the VibeCore Finance Core and Adapter APIs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Self, TypedDict
from uuid import UUID

import httpx


@dataclass(frozen=True, slots=True)
class HealthStatus:
    """Liveness or readiness response returned by Core and Adapter endpoints."""

    status: str


class PartnerPayload(TypedDict, total=False):
    ruc: str
    dv: str
    legal_name: str
    trade_name: str | None
    is_customer: bool
    is_supplier: bool
    is_active: bool
    metadata: dict[str, Any]


class PartnerRecord(PartnerPayload, total=False):
    id: str
    created_at: str
    updated_at: str


class AccountPayload(TypedDict, total=False):
    code: str
    name: str
    account_type: str
    parent_id: str | None
    reconcile: bool
    allow_posting: bool
    is_active: bool
    metadata: dict[str, Any]


class AccountRecord(AccountPayload, total=False):
    id: str
    created_at: str
    updated_at: str


class TaxPayload(TypedDict, total=False):
    code: str
    name: str
    rate: str
    scope: str
    sales_account_id: str | None
    purchase_account_id: str | None
    is_active: bool
    metadata: dict[str, Any]


class TaxRecord(TaxPayload, total=False):
    id: str
    created_at: str
    updated_at: str


class ProductPayload(TypedDict, total=False):
    sku: str
    name: str
    description: str | None
    unit_of_measure: str
    is_sales_item: bool
    is_purchase_item: bool
    standard_price: str
    default_tax_id: str | None
    income_account_id: str | None
    expense_account_id: str | None
    is_active: bool
    metadata: dict[str, Any]


class ProductRecord(ProductPayload, total=False):
    id: str
    created_at: str
    updated_at: str


class DocumentItemPayload(TypedDict, total=False):
    product_id: str | None
    tax_id: str
    product_code: str | None
    description: str
    unit_of_measure: str
    quantity: str
    unit_price: str
    discount_amount: str
    metadata: dict[str, Any]


class DocumentPayload(TypedDict, total=False):
    document_type: str
    direction: str
    created_by_actor: str
    partner_id: str
    associated_document_id: str | None
    issued_at: str
    due_date: str | None
    partner_reference: str | None
    currency_code: str
    functional_currency_code: str
    exchange_rate: str
    issuer_ruc: str
    issuer_dv: str
    issuer_legal_name: str
    is_electronic: bool
    timbrado_number: str
    establishment_code: str
    point_of_issue_code: str
    sifen_document_type: str | None
    sifen_emission_type: str | None
    sifen_document_number: str
    sifen_series: str
    sifen_cdc: str | None
    sifen_security_code: str | None
    items: list[DocumentItemPayload]
    metadata: dict[str, Any]


class DocumentRecord(DocumentPayload, total=False):
    id: str
    status: str
    subtotal: str
    tax_total: str
    total: str
    functional_subtotal: str
    functional_tax_total: str
    functional_total: str
    total_quantity: str
    partner_ruc: str
    partner_dv: str
    partner_legal_name: str
    sifen_status: str
    sifen_result: dict[str, Any]
    created_at: str
    updated_at: str


class JournalLinePayload(TypedDict, total=False):
    account_id: str
    description: str | None
    debit: str
    credit: str
    metadata: dict[str, Any]


class JournalEntryPayload(TypedDict, total=False):
    created_by_actor: str
    entry_date: str
    description: str
    reference: str | None
    source_document_id: str | None
    reverses_entry_id: str | None
    currency_code: str
    functional_currency_code: str
    exchange_rate: str
    lines: list[JournalLinePayload]
    metadata: dict[str, Any]


class JournalEntryPostPayload(TypedDict):
    approved_by_actor: str
    approved_by_role: str


class JournalEntryRecord(JournalEntryPayload, total=False):
    id: str
    status: str
    posted_at: str | None
    posted_by_actor: str | None
    posted_by_role: str | None
    created_at: str
    updated_at: str


class SifenSubmitPayload(TypedDict, total=False):
    header: dict[str, Any]
    items: list[dict[str, Any]]
    profile: dict[str, Any]
    meta: dict[str, Any]
    custom_data: dict[str, Any]


class SifenOutboxRecord(TypedDict, total=False):
    cdc: str
    dte_type: int
    status: str
    sifen_code: str | None
    sifen_message: str | None
    protocol_number: str | None
    retry_count: int
    last_error: str | None
    meta: dict[str, Any] | None
    custom_data: dict[str, Any] | None


class SifenFlushResult(TypedDict, total=False):
    processed_count: int
    accepted_count: int
    rejected_count: int
    still_queued_count: int
    items: list[SifenOutboxRecord]


class PagoparOrderPayload(TypedDict, total=False):
    order_id: str
    monto_total: float
    descripcion_resumen: str
    fecha_maxima_pago: str
    comprador: dict[str, Any]
    compras_items: list[dict[str, Any]]
    meta: dict[str, Any]
    custom_data: dict[str, Any]


class PagoparOrderRecord(TypedDict, total=False):
    order_id: str
    pagopar_hash: str
    status: str
    checkout_url: str
    amount_pyg: float
    meta: dict[str, Any] | None
    custom_data: dict[str, Any] | None


class StripeCheckoutPayload(TypedDict, total=False):
    order_id: str
    amount_total: float
    currency: str
    description: str
    customer_email: str | None
    success_url: str
    cancel_url: str
    meta: dict[str, Any]
    custom_data: dict[str, Any]


class StripePaymentIntentPayload(TypedDict, total=False):
    order_id: str
    amount: float
    currency: str
    description: str
    customer_email: str | None
    meta: dict[str, Any]
    custom_data: dict[str, Any]


class StripePaymentRecord(TypedDict, total=False):
    order_id: str
    stripe_id: str
    status: str
    checkout_url: str | None
    client_secret: str | None
    amount: float
    amount_cents: int
    currency: str


class MailSendPayload(TypedDict, total=False):
    to: list[str]
    cc: list[str]
    bcc: list[str]
    subject: str
    text_body: str
    html_body: str
    template_id: str
    template_data: dict[str, Any]
    attachments: list[dict[str, Any]]
    meta: dict[str, Any]
    custom_data: dict[str, Any]


class MailSendResult(TypedDict, total=False):
    message_id: str
    status: str
    queued_at: str


class WhatsAppTemplatePayload(TypedDict, total=False):
    to: str
    template_name: str
    language_code: str
    body_parameters: list[str]
    button_parameters: list[str]
    meta: dict[str, Any]
    custom_data: dict[str, Any]


class WhatsAppOtpSendPayload(TypedDict, total=False):
    phone_number: str
    purpose: str
    expiry_seconds: int
    template_name: str
    language_code: str
    meta: dict[str, Any]
    custom_data: dict[str, Any]


class WhatsAppOtpVerifyPayload(TypedDict, total=False):
    phone_number: str
    code: str
    purpose: str
    meta: dict[str, Any]
    custom_data: dict[str, Any]


class WhatsAppSendResult(TypedDict, total=False):
    success: bool
    message_id: str
    recipient: str
    status: str
    meta: dict[str, Any] | None
    custom_data: dict[str, Any] | None


class StoragePresignedUploadPayload(TypedDict, total=False):
    filename: str
    content_type: str
    file_id: str | None
    ttl_seconds: int
    sha256_hash: str | None
    custom_metadata: dict[str, str] | None


class StoragePresignedDownloadPayload(TypedDict, total=False):
    file_id: str
    ttl_seconds: int
    download_filename: str | None


class StoragePresignedResult(TypedDict, total=False):
    file_id: str
    bucket: str
    upload_url: str
    download_url: str
    expires_in_seconds: int


def _id_str(resource_id: str | UUID) -> str:
    return str(resource_id)


def _header_map(
    *,
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
    return headers


class CoreClient:
    """Typed synchronous client for the authenticated VibeCore Finance Core API."""

    def __init__(
        self,
        base_url: str,
        *,
        access_token: str,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
            transport=transport,
        )

    def health(self) -> HealthStatus:
        """Check the Core API liveness endpoint (/api/v1/health)."""
        response = self._client.get("/api/v1/health")
        response.raise_for_status()
        return HealthStatus(status=response.json()["status"])

    def ready(self) -> HealthStatus:
        """Check the Core API database readiness endpoint (/api/v1/ready)."""
        response = self._client.get("/api/v1/ready")
        response.raise_for_status()
        return HealthStatus(status=response.json()["status"])

    # --- Partners ---

    def create_partner(self, data: PartnerPayload | Mapping[str, Any]) -> PartnerRecord:
        """Create a fiscal partner (customer/supplier with RUC and DV)."""
        response = self._client.post("/api/v1/partners", json=dict(data))
        response.raise_for_status()
        return response.json()

    def get_partner(self, partner_id: str | UUID) -> PartnerRecord:
        """Retrieve a partner by ID."""
        response = self._client.get(f"/api/v1/partners/{_id_str(partner_id)}")
        response.raise_for_status()
        return response.json()

    def list_partners(self, offset: int = 0, limit: int = 100) -> list[PartnerRecord]:
        """List fiscal partners."""
        response = self._client.get("/api/v1/partners", params={"offset": offset, "limit": limit})
        response.raise_for_status()
        return response.json()

    def update_partner(
        self, partner_id: str | UUID, data: Mapping[str, Any]
    ) -> PartnerRecord:
        """Partially update a partner by ID."""
        response = self._client.patch(f"/api/v1/partners/{_id_str(partner_id)}", json=dict(data))
        response.raise_for_status()
        return response.json()

    def delete_partner(self, partner_id: str | UUID) -> None:
        """Delete an unreferenced partner by ID."""
        response = self._client.delete(f"/api/v1/partners/{_id_str(partner_id)}")
        response.raise_for_status()

    # --- Chart of Accounts ---

    def create_account(self, data: AccountPayload | Mapping[str, Any]) -> AccountRecord:
        """Create a chart-of-accounts entry."""
        response = self._client.post("/api/v1/accounts", json=dict(data))
        response.raise_for_status()
        return response.json()

    def get_account(self, account_id: str | UUID) -> AccountRecord:
        """Retrieve an account by ID."""
        response = self._client.get(f"/api/v1/accounts/{_id_str(account_id)}")
        response.raise_for_status()
        return response.json()

    def list_accounts(self, offset: int = 0, limit: int = 100) -> list[AccountRecord]:
        """List chart-of-accounts entries."""
        response = self._client.get("/api/v1/accounts", params={"offset": offset, "limit": limit})
        response.raise_for_status()
        return response.json()

    def update_account(
        self, account_id: str | UUID, data: Mapping[str, Any]
    ) -> AccountRecord:
        """Partially update a chart-of-accounts entry."""
        response = self._client.patch(f"/api/v1/accounts/{_id_str(account_id)}", json=dict(data))
        response.raise_for_status()
        return response.json()

    def delete_account(self, account_id: str | UUID) -> None:
        """Delete an unreferenced account by ID."""
        response = self._client.delete(f"/api/v1/accounts/{_id_str(account_id)}")
        response.raise_for_status()

    # --- Taxes (Paraguayan IVA Ley 6380/19) ---

    def create_tax(self, data: TaxPayload | Mapping[str, Any]) -> TaxRecord:
        """Create a Paraguayan IVA tax definition (0%, 5%, or 10%)."""
        response = self._client.post("/api/v1/taxes", json=dict(data))
        response.raise_for_status()
        return response.json()

    def get_tax(self, tax_id: str | UUID) -> TaxRecord:
        """Retrieve a tax definition by ID."""
        response = self._client.get(f"/api/v1/taxes/{_id_str(tax_id)}")
        response.raise_for_status()
        return response.json()

    def list_taxes(self, offset: int = 0, limit: int = 100) -> list[TaxRecord]:
        """List Paraguayan IVA tax definitions."""
        response = self._client.get("/api/v1/taxes", params={"offset": offset, "limit": limit})
        response.raise_for_status()
        return response.json()

    def update_tax(self, tax_id: str | UUID, data: Mapping[str, Any]) -> TaxRecord:
        """Partially update a tax definition."""
        response = self._client.patch(f"/api/v1/taxes/{_id_str(tax_id)}", json=dict(data))
        response.raise_for_status()
        return response.json()

    def delete_tax(self, tax_id: str | UUID) -> None:
        """Delete an unreferenced tax definition."""
        response = self._client.delete(f"/api/v1/taxes/{_id_str(tax_id)}")
        response.raise_for_status()

    # --- Products ---

    def create_product(self, data: ProductPayload | Mapping[str, Any]) -> ProductRecord:
        """Create a financial/tax reference product item."""
        response = self._client.post("/api/v1/products", json=dict(data))
        response.raise_for_status()
        return response.json()

    def get_product(self, product_id: str | UUID) -> ProductRecord:
        """Retrieve a product by ID."""
        response = self._client.get(f"/api/v1/products/{_id_str(product_id)}")
        response.raise_for_status()
        return response.json()

    def list_products(self, offset: int = 0, limit: int = 100) -> list[ProductRecord]:
        """List financial reference products."""
        response = self._client.get("/api/v1/products", params={"offset": offset, "limit": limit})
        response.raise_for_status()
        return response.json()

    def update_product(
        self, product_id: str | UUID, data: Mapping[str, Any]
    ) -> ProductRecord:
        """Partially update a product by ID."""
        response = self._client.patch(f"/api/v1/products/{_id_str(product_id)}", json=dict(data))
        response.raise_for_status()
        return response.json()

    def delete_product(self, product_id: str | UUID) -> None:
        """Delete an unreferenced product by ID."""
        response = self._client.delete(f"/api/v1/products/{_id_str(product_id)}")
        response.raise_for_status()

    # --- Commercial Reference Documents ---

    def create_document(self, data: DocumentPayload | Mapping[str, Any]) -> DocumentRecord:
        """Create a DRAFT reference commercial document with gross-inclusive IVA calculation."""
        response = self._client.post("/api/v1/documents", json=dict(data))
        response.raise_for_status()
        return response.json()

    def get_document(self, document_id: str | UUID) -> DocumentRecord:
        """Retrieve a commercial document by ID."""
        response = self._client.get(f"/api/v1/documents/{_id_str(document_id)}")
        response.raise_for_status()
        return response.json()

    def list_documents(self, offset: int = 0, limit: int = 100) -> list[DocumentRecord]:
        """List commercial documents."""
        response = self._client.get("/api/v1/documents", params={"offset": offset, "limit": limit})
        response.raise_for_status()
        return response.json()

    def update_document(
        self, document_id: str | UUID, data: Mapping[str, Any]
    ) -> DocumentRecord:
        """Update header fields on a DRAFT commercial document."""
        response = self._client.patch(f"/api/v1/documents/{_id_str(document_id)}", json=dict(data))
        response.raise_for_status()
        return response.json()

    def delete_document(self, document_id: str | UUID) -> None:
        """Delete a DRAFT commercial document."""
        response = self._client.delete(f"/api/v1/documents/{_id_str(document_id)}")
        response.raise_for_status()

    # --- Double-Entry Journal Entries ---

    def create_journal_entry(
        self, data: JournalEntryPayload | Mapping[str, Any]
    ) -> JournalEntryRecord:
        """Create a balanced double-entry journal entry header and lines in DRAFT status."""
        response = self._client.post("/api/v1/journal-entries", json=dict(data))
        response.raise_for_status()
        return response.json()

    def get_journal_entry(self, journal_entry_id: str | UUID) -> JournalEntryRecord:
        """Retrieve a journal entry by ID."""
        response = self._client.get(f"/api/v1/journal-entries/{_id_str(journal_entry_id)}")
        response.raise_for_status()
        return response.json()

    def list_journal_entries(
        self, offset: int = 0, limit: int = 100
    ) -> list[JournalEntryRecord]:
        """List journal entries."""
        response = self._client.get(
            "/api/v1/journal-entries", params={"offset": offset, "limit": limit}
        )
        response.raise_for_status()
        return response.json()

    def update_journal_entry(
        self, journal_entry_id: str | UUID, data: Mapping[str, Any]
    ) -> JournalEntryRecord:
        """Update header fields on a DRAFT journal entry."""
        response = self._client.patch(
            f"/api/v1/journal-entries/{_id_str(journal_entry_id)}", json=dict(data)
        )
        response.raise_for_status()
        return response.json()

    def delete_journal_entry(self, journal_entry_id: str | UUID) -> None:
        """Delete a DRAFT journal entry."""
        response = self._client.delete(f"/api/v1/journal-entries/{_id_str(journal_entry_id)}")
        response.raise_for_status()

    def submit_journal_entry(self, journal_entry_id: str | UUID) -> JournalEntryRecord:
        """Transition a balanced DRAFT journal entry to PENDING_APPROVAL."""
        response = self._client.post(
            f"/api/v1/journal-entries/{_id_str(journal_entry_id)}/submit"
        )
        response.raise_for_status()
        return response.json()

    def post_journal_entry(
        self,
        journal_entry_id: str | UUID,
        data: JournalEntryPostPayload | Mapping[str, Any],
    ) -> JournalEntryRecord:
        """Post and lock a PENDING_APPROVAL journal entry with four-eyes human approval."""
        response = self._client.post(
            f"/api/v1/journal-entries/{_id_str(journal_entry_id)}/post", json=dict(data)
        )
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class AdapterClient:
    """Minimal, typed HTTP client for isolated VibeCore Microservice Adapters."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            headers["X-Adapter-Key"] = api_key
            headers["X-API-Key"] = api_key
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    def health(self) -> HealthStatus:
        """Check the adapter liveness endpoint (/health)."""
        response = self._client.get("/health")
        response.raise_for_status()
        return HealthStatus(status=response.json()["status"])

    def ready(self) -> dict[str, Any]:
        """Check the adapter readiness endpoint (/ready)."""
        response = self._client.get("/ready")
        response.raise_for_status()
        return response.json()

    # --- SIFEN Fiscal Adapter ---

    def resolve_sifen_profile(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """Resolve a Paraguayan Mandant RUC profile into DTE type and IVA regime."""
        response = self._client.post("/api/v1/sifen/resolve", json=dict(data))
        response.raise_for_status()
        return response.json()

    def submit_sifen_dte(
        self,
        data: SifenSubmitPayload | Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> SifenOutboxRecord:
        """Generate and submit a DTE to SIFEN with persistent Outbox fallback."""
        response = self._client.post(
            "/api/v1/sifen/submit",
            json=dict(data),
            headers=_header_map(idempotency_key=idempotency_key, correlation_id=correlation_id),
        )
        response.raise_for_status()
        return response.json()

    def flush_sifen_outbox(self, *, correlation_id: str | None = None) -> SifenFlushResult:
        """Flush queued DTEs from the persistent SIFEN Outbox Queue."""
        response = self._client.post(
            "/api/v1/sifen/outbox/flush",
            headers=_header_map(correlation_id=correlation_id),
        )
        response.raise_for_status()
        return response.json()

    def get_sifen_dte(self, cdc: str) -> SifenOutboxRecord:
        """Retrieve SIFEN DTE submission status by 44-digit CDC."""
        response = self._client.get(f"/api/v1/sifen/outbox/{cdc}")
        response.raise_for_status()
        return response.json()

    # --- Pagopar Payment Adapter ---

    def create_pagopar_order(
        self,
        data: PagoparOrderPayload | Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> PagoparOrderRecord:
        """Initiate a Pagopar payment order and obtain checkout URL."""
        response = self._client.post(
            "/api/v1/pagopar/orders",
            json=dict(data),
            headers=_header_map(idempotency_key=idempotency_key, correlation_id=correlation_id),
        )
        response.raise_for_status()
        return response.json()

    def get_pagopar_order(self, order_id: str) -> PagoparOrderRecord:
        """Retrieve Pagopar order status by order_id."""
        response = self._client.get(f"/api/v1/pagopar/orders/{order_id}")
        response.raise_for_status()
        return response.json()

    def sync_pagopar_order(
        self, order_id: str, *, correlation_id: str | None = None
    ) -> dict[str, Any]:
        """Synchronize Pagopar order payment status for recovery."""
        response = self._client.post(
            f"/api/v1/pagopar/orders/{order_id}/sync",
            headers=_header_map(correlation_id=correlation_id),
        )
        response.raise_for_status()
        return response.json()

    # --- Stripe Payment Adapter ---

    def create_stripe_checkout_session(
        self,
        data: StripeCheckoutPayload | Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> StripePaymentRecord:
        """Create a Stripe Checkout Session."""
        response = self._client.post(
            "/api/v1/stripe/checkout-sessions",
            json=dict(data),
            headers=_header_map(idempotency_key=idempotency_key, correlation_id=correlation_id),
        )
        response.raise_for_status()
        return response.json()

    def create_stripe_payment_intent(
        self,
        data: StripePaymentIntentPayload | Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> StripePaymentRecord:
        """Create a direct Stripe PaymentIntent."""
        response = self._client.post(
            "/api/v1/stripe/payment-intents",
            json=dict(data),
            headers=_header_map(idempotency_key=idempotency_key, correlation_id=correlation_id),
        )
        response.raise_for_status()
        return response.json()

    def get_stripe_payment(self, payment_id: str) -> StripePaymentRecord:
        """Retrieve Stripe payment status by order_id or stripe_id."""
        response = self._client.get(f"/api/v1/stripe/payments/{payment_id}")
        response.raise_for_status()
        return response.json()

    def sync_stripe_payment(
        self, payment_id: str, *, correlation_id: str | None = None
    ) -> dict[str, Any]:
        """Synchronize Stripe payment status for recovery."""
        response = self._client.post(
            f"/api/v1/stripe/payments/{payment_id}/sync",
            headers=_header_map(correlation_id=correlation_id),
        )
        response.raise_for_status()
        return response.json()

    # --- Mail Adapter ---

    def send_mail(
        self,
        data: MailSendPayload | Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> MailSendResult:
        """Enqueue an outbound email via the vc-mail microservice."""
        response = self._client.post(
            "/api/v1/mail/send",
            json=dict(data),
            headers=_header_map(idempotency_key=idempotency_key, correlation_id=correlation_id),
        )
        response.raise_for_status()
        return response.json()

    def get_mail_status(self, message_id: str) -> dict[str, Any]:
        """Retrieve delivery status of a queued email message."""
        response = self._client.get(f"/api/v1/mail/status/{message_id}")
        response.raise_for_status()
        return response.json()

    # --- WhatsApp Cloud API Adapter ---

    def send_whatsapp_template(
        self, data: WhatsAppTemplatePayload | Mapping[str, Any]
    ) -> WhatsAppSendResult:
        """Send a pre-approved template notification via WhatsApp Cloud API."""
        response = self._client.post("/api/v1/messages/send-template", json=dict(data))
        response.raise_for_status()
        return response.json()

    def send_whatsapp_otp(
        self, data: WhatsAppOtpSendPayload | Mapping[str, Any]
    ) -> dict[str, Any]:
        """Generate and transmit a one-time password via WhatsApp."""
        response = self._client.post("/api/v1/otp/send", json=dict(data))
        response.raise_for_status()
        return response.json()

    def verify_whatsapp_otp(
        self, data: WhatsAppOtpVerifyPayload | Mapping[str, Any]
    ) -> dict[str, Any]:
        """Verify a submitted WhatsApp OTP code."""
        response = self._client.post("/api/v1/otp/verify", json=dict(data))
        response.raise_for_status()
        return response.json()

    # --- S3 Object Storage Adapter ---

    def create_presigned_upload(
        self, data: StoragePresignedUploadPayload | Mapping[str, Any]
    ) -> StoragePresignedResult:
        """Generate a presigned S3 upload URL."""
        response = self._client.post("/api/v1/storage/presigned-upload", json=dict(data))
        response.raise_for_status()
        return response.json()

    def create_presigned_download(
        self, data: StoragePresignedDownloadPayload | Mapping[str, Any]
    ) -> StoragePresignedResult:
        """Generate a presigned S3 download URL."""
        response = self._client.post("/api/v1/storage/presigned-download", json=dict(data))
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
