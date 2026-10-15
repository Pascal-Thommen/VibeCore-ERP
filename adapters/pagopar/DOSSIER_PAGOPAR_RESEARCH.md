# Pagopar API v2 Recherche und Spezifikationsdossier

Dieses Dokument fasst die Ergebnisse der Phase 1 (Recherche und Wiederverwendungs-Prüfung) für die Integration des paraguayischen Zahlungsdienstleisters Pagopar in das VibeCore ERP Ökosystem zusammen.

## 1. Analyse vorhandener Open-Source-Bibliotheken und SDKs

### Evaluierte Bibliotheken
1. **`pagopar` (PyPI Version 1.0.0 von Alan Bogarin):**
   * Architektur: Basiert auf `aiohttp` und `msgspec`.
   * Funktionsumfang: Bietet grundlegende Aufrufe für Transaktionsstart, Abfrage von Zahlungsmethoden und Courier-Dienste.
   * Schwachstellen für Enterprise ERP:
     * Verwendet `msgspec` anstelle des VibeCore Standardframeworks Pydantic v2.
     * Enthält keine persistente Idempotenzprüfung für Webhooks.
     * Bietet keine strukturierte Fehlerbehandlung mit Retry- und Circuit-Breaker-Strategien für Netzwerkausfälle.
     * Keine native Integration in FastAPI oder SQLAlchemy für lokale Transaktionsprotokollierung.
     * Abhängigkeit von einem einzelnen externen Maintainer ohne breite Community-Basis.

2. **Legacy Python Wrapper (`pypagopar` und inoffizielle Skripte):**
   * Stand: Entwickelt für Pagopar API v1.1, teilweise seit 2018 nicht mehr aktualisiert.
   * Inkompatibilität: Die alten Skripte unterstützen die Pagopar API v2 mit modernem JSON-Payload nicht und arbeiten mit veralteten Signaturen.

3. **PHP und Node.js Referenzimplementierungen von Pagopar:**
   * Die offiziellen Pagopar-Plugins (z. B. für WooCommerce, PrestaShop) sind in PHP verfasst. Sie dienen als funktionale Referenz für die kryptografische Token-Berechnung und das Webhook-Verhalten.

### Fazit und Architekturentscheidung
Gemäß ADR 0008 (Mature Library Implementation Policy) und der VibeCore Zero-Mock-Doktrin erfolgt die Implementierung als nativer, autonomer Microservice mit FastAPI, Pydantic v2, HTTPX und SQLAlchemy (SQLite / PostgreSQL Outbox). Anstelle unvollständiger Drittanbieter-Wrapper werden etablierte Standardbibliotheken (`hashlib`, `hmac`, `httpx`, `pydantic`) genutzt, um ein robustes, auditiertes und wartbares Adapter-System bereitzustellen.

---

## 2. Detaillierte Spezifikation der Pagopar REST-Endpunkte

### 2.1 Umgebungen und Basis-URLs
* **Produktionsumgebung:** `https://api.pagopar.com`
* **Sandbox / Testumgebung:** `https://api-sandbox.pagopar.com` (bzw. konfigurierbare Entwicklungs-URL)
* **Checkout-URL Produktion:** `https://www.pagopar.com/pagos/{hash_transaccion}`
* **Checkout-URL Sandbox:** `https://sandbox.pagopar.com/pagos/{hash_transaccion}` (oder `https://www.pagopar.com/pagos/{hash_transaccion}`)

---

### 2.2 Initiierung von Zahlungen (Creación de Pedidos / Iniciar Transacción)

* **Endpunkt:** `POST /api/comercios/2.0/iniciar-transaccion`
* **Content-Type:** `application/json`
* **Zweck:** Initialisiert einen Bezahlvorgang, registriert den Käufer und Warenkorb bei Pagopar und liefert das Transaktions-Hash zurück.

#### Kryptografische Signatur (Token-Berechnung)
Der Parameter `token` sichert den Request gegen Manipulationen ab. Er wird mittels SHA-1 gebildet:
```
Token = SHA1(private_key + id_pedido_comercio + str(float(monto_total)))
```
* `private_key`: Geheimer Schlüssel des Händlers aus dem Pagopar Dashboard.
* `id_pedido_comercio`: Eindeutige Bestellnummer des ERP-Systems.
* `monto_total`: Gesamtbetrag als Fließkommazahl im String-Format (z. B. "100000.0").

#### Request Payload Parameter
* `token` (string, Pflicht): Der oben berechnete SHA-1 Hash.
* `public_key` (string, Pflicht): Öffentlicher Händlerschlüssel.
* `tipo_pedido` (string, Pflicht): Typ der Transaktion, Standard: `"VENTA-COMERCIO"`.
* `operation_type` (string, optional): `"sale"`.
* `monto_total` (number, Pflicht): Gesamtbetrag in Guaraníes (PYG).
* `id_pedido_comercio` (string oder int, Pflicht): Bestellnummer im Mandantensystem.
* `descripcion_resumen` (string, Pflicht): Kurzbeschreibung für den Kunden.
* `fecha_maxima_pago` (string, Pflicht): Ablaufdatum des Zahlungsangebots im Format `"YYYY-MM-DD HH:MM:SS"`.
* `comprador` (object, Pflicht): Käuferdaten
  * `ruc` (string): RUC oder Steuernummer des Käufers.
  * `documento` (string): Ausweisnummer (z. B. C.I.).
  * `tipo_documento` (string): Ausweistyp (`"CI"`, `"RUC"`, `"PAS"`).
  * `nombre` (string): Vorname oder vollständiger Name.
  * `razon_social` (string): Firmenname oder Name für Rechnungsstellung.
  * `email` (string): E-Mail-Adresse für Zahlungsbestätigung.
  * `telefono` (string): Telefonnummer / WhatsApp-Kontakt.
  * `direccion` (string): Anschrift des Kunden.
* `compras_items` (array von Objekten, Pflicht): Einzelpositionen des Auftrags
  * `id_producto` (string oder int): Artikelnummer.
  * `nombre` (string): Bezeichnung des Artikels / Dienstleistung.
  * `cantidad` (int): Menge (mindestens 1).
  * `precio_total` (number): Gesamtpreis der Position in PYG.
  * `categoria` (string): Kategorie-Code bei Pagopar (z. B. `"99"` für Dienstleistungen oder Software).
  * `public_key` (string): Öffentlicher Händlerschlüssel.

#### Antwortformat (Pagopar Response)
```json
{
  "respuesta": true,
  "resultado": [
    {
      "data": "a3f5c7e9b1d2... (64-Zeichen Hash der Transaktion)"
    }
  ]
}
```
Bei `respuesta: true` wird die Checkout-URL aus dem Feld `data` erzeugt:
`checkout_url = f"{base_checkout_url}/{hash_transaccion}"`

---

### 2.3 Webhook-Callback (Notificación de Pago)

* **Endpunkt im Microservice:** `POST /api/v1/pagopar/webhook`
* **Trigger:** Pagopar ruft diese URL automatisch per HTTP POST auf, sobald sich der Bezahlstatus einer Transaktion ändert.

#### Eingehende Webhook Payload Struktur
```json
{
  "respuesta": true,
  "resultado": [
    {
      "pagado": true,
      "fecha_pago": "2026-10-15 10:15:30",
      "forma_pago": "Tarjeta de Credito",
      "forma_pago_identificador": "1",
      "hash_pedido": "a3f5c7e9b1d2...",
      "monto": 150000,
      "token": "4e78b12f6a98...",
      "numero_comprobante": "87654321",
      "comentario": null,
      "identificador_pago": 987654
    }
  ]
}
```

#### Kryptografisches Signaturverfahren (Sicherheitsprüfung)
Zur Abwehr von Spoofing, Man-in-the-Middle und manipulierten Payloads berechnet der Adapter die erwartete Signatur:
```
Token_Erwartet = SHA1(private_key + hash_pedido)
```
* Der Vergleich zwischen `Token_Erwartet` und dem erhaltenen `resultado[0].token` erfolgt mittels zeitkonstanter String-Vergleichsfunktion (`hmac.compare_digest`), um Timing-Attacks auszuschließen.
* Stimmt die Signatur nicht überein, wird der Request sofort mit HTTP 403 Forbidden abgewiesen und ein Sicherheitsalarm im Audit-Log vermerkt.

#### Idempotenz und Antwortverhalten
* Mehrfache Webhooks (Pagopar wiederholt Benachrichtigungen bis zu 24 Stunden bei Nichterreichbarkeit) werden anhand von `hash_pedido` und `identificador_pago` in der lokalen Datenbank abgeglichen.
* Ist ein Webhook bereits verarbeitet, wird die Aktion nicht erneut ausgeführt, sondern direkt mit HTTP 200 quittiert.
* Nach erfolgreicher Verarbeitung antwortet der Service mit HTTP 200 und dem Bestätigungs-JSON.

---

### 2.4 Polling-Endpunkt für Transaktionsstatus (Traer Pedido)

* **Endpunkt bei Pagopar:** `POST /api/pedidos/1.1/traer`
* **Zweck:** Dient als asynchrone Ausfallabsicherung, falls der Webhook durch Netzwerkstörungen oder Firewall-Blockaden nicht zugestellt werden konnte.

#### Token-Berechnung für die Statusabfrage
```
Token_Abfrage = SHA1(private_key + "CONSULTA")
```

#### Request Payload
```json
{
  "token_publico": "<PAGOPAR_PUBLIC_KEY>",
  "token": "<Token_Abfrage>",
  "hash_pedido": "<hash_transaccion>"
}
```

#### Antwortformat
```json
{
  "respuesta": true,
  "resultado": [
    {
      "pagado": true,
      "forma_pago": "SIPAP QR",
      "monto": "150000.00",
      "numero_pedido": "ORD-2026-001",
      "fecha_pago": "2026-10-15 10:15:30"
    }
  ]
}
```
Liefert `pagado: true`, wird die lokale Transaktion auf `PAID` aktualisiert und das entsprechende Outbox-Event ausgelöst.

---

## 3. Architektur der Eigenentwicklung im VibeCore Ökosystem

1. **Separation of Concerns:**
   * Der Pagopar Adapter läuft als eigenständiger Container.
   * Keine direkte Verbindung zur Core PostgreSQL Datenbank.
   * Kommunikation mit dem VibeCore Core erfolgt über REST-Endpunkte und signierte Events.

2. **Resilienz und lokale Persistenz:**
   * Lokales Transaktions- und Audit-Log auf Basis von SQLAlchemy mit SQLite (bzw. optional Postgres).
   * Persistente Speicherung aller Zustandsübergänge (`INITIATED`, `PENDING_PAYMENT`, `PAID`, `EXPIRED`, `FAILED`).
   * Saubere Timeouts (10 Sekunden) und Exponential Backoff Retries bei transienten Verbindungsproblemen zu Pagopar.

3. **Sicherheit und Observability:**
   * Konfiguration ausschließlich über Umgebungsvariablen (`PAGOPAR_PUBLIC_KEY`, `PAGOPAR_PRIVATE_KEY`, `PAGOPAR_ENV`, `ADAPTER_API_KEY`).
   * Strukturierte JSON Logs mit Korrelations-IDs (`X-Correlation-ID`).
   * Standardisierte `/health` und `/ready` Healthchecks.
