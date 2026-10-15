# VibeCore Python SDK (`vibecore-sdk`)

Universelles, stark typisiertes Python SDK zur nahtlosen Anbindung des VibeCore Finance Core und aller modularen Microservice-Adapter.

## Übersicht der Module und Clients

Das SDK ist modular unter `vibecore` strukturiert:

* `vibecore.core.CoreClient`: Doppelte Buchführung, Kontenplan und Journal-Entries.
* `vibecore.auth.AuthClient`: Google OAuth 2.0 / OIDC SSO, PKCE Login, Session-Validierung (`/auth/me`) und Logout.
* `vibecore.storage.StorageClient`: S3-kompatibler Objektspeicher, Direct Streaming Upload, Presigned URLs, Metadaten und Löschung.
* `vibecore.payments.pagopar.PagoparClient`: Paraguayisches Zahlungsgateway (Bancard, PagoMóvil, Billeteras).
* `vibecore.payments.stripe.StripeClient`: Internationales Kreditkarten- und Zahlungs-Gateway (Checkout Sessions, PaymentIntents).
* `vibecore.client.VibeCoreClient`: Zentraler Einstiegspunkt und Context Manager mit Lazy-Loading aller Adapter.

## Installation

```bash
pip install ./sdk
```

Abhängigkeiten: Python >= 3.12, `httpx>=0.27`, `pydantic>=2.0`.

## Einheitliche Exception-Hierarchie

Alle SDK-Fehler erben von `VibeCoreError`:

* `VibeCoreError`: Basis-Klasse mit `status_code`, `message`, `detail` und `response`.
  * `AuthenticationError`: Authentifizierungs- oder CSRF-Fehler (401, 403).
  * `StorageError`: Basis-Fehler für den Storage-Adapter.
    * `StorageNotFoundError`: Datei nicht gefunden (404).
    * `StorageValidationError`: Validierungsfehler bei Dateinamen oder Parametern (400).
    * `StorageAuthenticationError`: Ungültiger oder fehlender Storage API-Key (401, 403).
  * `PaymentError`: Basis-Fehler für Zahlungsadapter.
    * `PaymentNotFoundError`: Order oder Zahlung nicht gefunden (404).
    * `PaymentGatewayError`: Upstream-Gateway meldet Fehler (502).
    * `PaymentTimeoutError`: Upstream-Gateway antwortet nicht innerhalb des Timeouts (504).
  * `NetworkError`: Verbindungsausfall oder DNS-Fehler.
  * `TimeoutError`: Überschreitung des konfigurierten Timeouts.

## Anwendungsbeispiele

### 1. Unified Client (`VibeCoreClient`)

```python
from vibecore import VibeCoreClient

with VibeCoreClient(
    core_url="http://localhost:8000",
    core_token="jwt_secret_token",
    auth_url="http://localhost:8001",
    storage_url="http://localhost:8002",
    storage_api_key="storage_secret_key",
    pagopar_url="http://localhost:8003",
    pagopar_api_key="pagopar_adapter_key",
    stripe_url="http://localhost:8004",
    stripe_api_key="stripe_adapter_key",
) as client:
    # Core Health
    core_health = client.core.health()
    print("Core Status:", core_health.status)

    # Auth Login URL
    login_info = client.auth.get_login_url(redirect_after_login="https://app.vibecore.io")
    print("Google OAuth URL:", login_info.authorization_url)
```

### 2. AuthClient (Google OAuth 2.0 / OIDC SSO)

```python
from vibecore.auth import AuthClient
from vibecore.exceptions import AuthenticationError

client = AuthClient("http://localhost:8001")

# Login initialisieren
init = client.get_login_url(redirect_after_login="https://app.vibecore.io/dashboard")
print("Redirect to:", init.authorization_url)
print("State Token:", init.state)

# Code Exchange nach Callback
try:
    tokens = client.exchange_code(code="4/0AWgav...", state=init.state)
    print("Access Token:", tokens.access_token)
    print("User Email:", tokens.user.email)
    print("Roles:", tokens.user.roles)

    # Session validieren (/auth/me)
    user_info = client.get_current_user(tokens.access_token)
    print("Validated User:", user_info.name)
except AuthenticationError as e:
    print(f"Login fehlgeschlagen ({e.status_code}):", e.message)
finally:
    client.close()
```

### 3. StorageClient (S3 Object Storage)

```python
from vibecore.storage import StorageClient
from vibecore.exceptions import StorageNotFoundError

with StorageClient("http://localhost:8002", api_key="storage_secret_key") as client:
    # Direct Streaming Upload
    with open("rechnung_2026.pdf", "rb") as f:
        upload_res = client.upload(
            file=f,
            filename="rechnung_2026.pdf",
            content_type="application/pdf",
            file_id="invoices/2026/rec_001.pdf",
            custom_metadata={"tax_year": "2026", "iva": "10"},
        )
    print("File ID:", upload_res.file_id)
    print("SHA-256:", upload_res.sha256_hash)

    # Presigned Download URL anfordern
    download = client.get_presigned_download_url("invoices/2026/rec_001.pdf", ttl_seconds=1800)
    print("Download URL:", download.download_url)

    # Metadaten abrufen
    try:
        meta = client.get_metadata("invoices/2026/rec_001.pdf")
        print("Größe:", meta.size_bytes, "Bytes")
    except StorageNotFoundError:
        print("Datei nicht gefunden.")
```

### 4. PagoparClient (Paraguay Payment Gateway)

```python
from vibecore.payments.pagopar import (
    BuyerModel,
    CreateOrderRequest,
    DocumentType,
    OrderItemModel,
    PagoparClient,
)
from vibecore.exceptions import PaymentGatewayError

client = PagoparClient("http://localhost:8003", api_key="pagopar_secret_key")

req = CreateOrderRequest(
    order_id="ORDER-PY-2026-001",
    monto_total=250000.0,
    descripcion_resumen="Jahreslizenz VibeCore ERP",
    comprador=BuyerModel(
        ruc="80012345-6",
        email="kunde@firma.com.py",
        nombre="Juan Perez",
        telefono="0981123456",
        documento="1234567",
        tipo_documento=DocumentType.CI,
        razon_social="Firma S.A.",
    ),
    compras_items=[
        OrderItemModel(
            id_producto="LIC-001",
            nombre="VibeCore Standard License",
            cantidad=1,
            precio_total=250000.0,
        )
    ],
)

try:
    order = client.create_order(req, idempotency_key="idemp-order-001")
    print("Checkout URL:", order.checkout_url)
    print("Status:", order.status)

    # Status synchronisieren
    sync_result = client.sync_order("ORDER-PY-2026-001")
    print("Aktueller Status:", sync_result.current_status)
except PaymentGatewayError as e:
    print("Gateway-Fehler:", e.message)
finally:
    client.close()
```

### 5. StripeClient (International Payments)

```python
from vibecore.payments.stripe import (
    CreateCheckoutSessionRequest,
    CreatePaymentIntentRequest,
    LineItemModel,
    StripeClient,
)

with StripeClient("http://localhost:8004", api_key="stripe_secret_key") as client:
    # Stripe Checkout Session
    session = client.create_checkout_session(
        CreateCheckoutSessionRequest(
            order_id="ORDER-INT-2026-002",
            amount_total=99.00,
            currency="USD",
            description="Enterprise AI Addon",
            customer_email="billing@globalcorp.com",
            success_url="https://app.vibecore.io/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://app.vibecore.io/cancel",
            items=[
                LineItemModel(
                    name="Enterprise AI Module",
                    amount=99.00,
                    quantity=1,
                    currency="USD",
                )
            ],
        ),
        idempotency_key="idemp-stripe-002",
    )
    print("Stripe Checkout URL:", session.checkout_url)
    print("Status:", session.status)
```

## Resilienz, Retries und Timeouts

Alle Clients unterstützen konfigurierbare Timeouts und automatische Wiederholungsversuche bei temporären Netzwerkunterbrechungen oder HTTP 502, 503, 504:

```python
from vibecore.storage import StorageClient

# Timeout auf 15 Sekunden, bis zu 5 automatische Wiederholungen mit Exponential Backoff
client = StorageClient(
    "http://localhost:8002",
    api_key="storage_secret",
    timeout=15.0,
    max_retries=5,
)
```
