# Stripe API Recherche und Spezifikationsdossier

Dieses Dokument fasst die Ergebnisse der Phase 1 (Recherche, SDK-Analyse und Schnittstellen-Harmonisierung) für die Integration des internationalen Zahlungsdienstleisters Stripe in das VibeCore ERP Ökosystem zusammen.

## 1. Analyse der Stripe REST API und Python SDK

### 1.1 Evaluierte Integrationspfade
1. **Offizielles Stripe Python SDK (`stripe` >= 11.0.0 / v16):**
   * Architektur: Bietet synchrone und asynchrone Bindings sowie eingebaute Klassen für Stripe Objects (`stripe.checkout.Session`, `stripe.PaymentIntent`, `stripe.Webhook`).
   * Stärken: Vollständige Typisierung, native kryptografische Hilfsfunktionen (`stripe.Webhook.construct_event`).
   * Schwachstellen für asynchrone Enterprise Microservices:
     * Historisch primär synchron aufgebaut; asynchrone Methoden erfordern spezifische Event-Loop-Konfigurationen.
     * Hohes Gewicht der Bibliothek mit häufigen Breaking Changes zwischen Major Versions.

2. **Direkte REST-API-Anbindung via `httpx.AsyncClient` (VibeCore Standard gemäß ADR 0008):**
   * Architektur: Hochperformante, native asynchrone HTTP-Aufrufe mit explizitem Timeout- und Retry-Management.
   * Transparenz: Vollständige Kontrolle über HTTP-Header (`Idempotency-Key`, `Stripe-Version`, `Authorization`), Correlation-IDs und Timeouts.
   * Zero-Mock-Doktrin: Keine unkontrollierten SDK-Verhaltensweisen bei Netzwerkabbrüchen.

### 1.2 Architekturentscheidung
Der `adapters/stripe` Microservice implementiert eine duale, resiliente Architektur:
* Der primäre HTTP-Client nutzt `httpx.AsyncClient` für atomare REST-Aufrufe gegen `https://api.stripe.com/v1`.
* Die kryptografische Signaturprüfung von Webhooks wird unabhängig und timing-sicher mittels nativer Python-Kryptografie (`hmac`, `hashlib`) mit konfigurierbarer Timestamp-Toleranz implementiert, um Abhängigkeiten zu isolieren.
* Sämtliche Datenstrukturen werden durch strikte Pydantic v2 Modelle validiert.

---

## 2. Kernkomponenten der Stripe Zahlungsabwicklung

### 2.1 Stripe Checkout Sessions (Gehostete Zahlungsseite)
* **Zweck:** Bereitstellung einer von Stripe gehosteten, PCI-DSS-konformen Bezahlseite für Kreditkarten, Apple Pay, Google Pay und länderspezifische Zahlungsmethoden.
* **Stripe REST Endpoint:** `POST https://api.stripe.com/v1/checkout/sessions`
* **Workflow im VibeCore ERP:**
  1. ERP initiiert `POST /api/v1/stripe/checkout-sessions` mit Auftrags-ID, Betrag, Währung und Positionen.
  2. Adapter transformiert Beträge in die kleinste Währungseinheit (Cents).
  3. Adapter ruft die Stripe API auf und empfängt die Session ID (`cs_...`) sowie die `url` (`https://checkout.stripe.com/c/pay/cs_...`).
  4. Adapter speichert den Status `PENDING_PAYMENT` atomar in der lokalen Datenbank.
  5. Der Kunde schließt die Zahlung auf der Stripe-Checkout-Seite ab.
  6. Stripe sendet den Webhook `checkout.session.completed` an den Adapter.

### 2.2 PaymentIntents (Direkte Zahlungsabwicklung)
* **Zweck:** Direkte Steuerung des Lebenszyklus einer Zahlung (z. B. für In-App-Zahlungen, wiederkehrende Zahlungen oder kundenspezifische Bezahlmasken).
* **Stripe REST Endpoint:** `POST https://api.stripe.com/v1/payment_intents`
* **Status-Lebenszyklus bei Stripe:**
  * `requires_payment_method`: Zahlung initiiert, Zahlungsdetails noch ausstehend.
  * `requires_confirmation`: Bereit zur Belastung.
  * `requires_action`: 3D-Secure oder Kundenauthentifizierung erforderlich.
  * `processing`: Zahlung in Bearbeitung.
  * `succeeded`: Zahlung erfolgreich abgeschlossen.
  * `canceled`: Zahlung storniert.

### 2.3 Cent-Betragslogik (Currency Smallest Units)
Stripe erwartet Beträge prinzipiell als Integer in der kleinsten Währungseinheit:
1. **Zwei-Dezimal-Währungen (z. B. USD, EUR, GBP, CHF, BRL):**
   * Multiplikationsfaktor: 100.
   * Beispiel: 10.50 USD wird als `1050` an Stripe übermittelt.
2. **Null-Dezimal-Währungen (z. B. JPY, KRW, PYG, CLP, VND):**
   * Multiplikationsfaktor: 1.
   * Beispiel: 15.000 PYG wird als `15000` an Stripe übermittelt.
3. **Drei-Dezimal-Währungen (z. B. BHD, KWD, OMR, TND):**
   * Multiplikationsfaktor: 1000.
   * Beispiel: 5.125 KWD wird als `5125` übermittelt.

Der Adapter implementiert eine bidirektionale Konvertierungsmethode, die Rundungsfehler ausschließt und Währungen strikt validiert.

### 2.4 Kryptografische Webhook-Signaturprüfung (HMAC-SHA256)
* **Stripe Webhook Header:** `Stripe-Signature`
* **Format des Headers:** `t=1729032000,v1=5257a869e7ecebeda32affa62cd496d1b9e67e47731ec2d599e773f577c39810,v0=...`
* **Signaturberechnung:**
  ```python
  signed_payload = f"{timestamp}.{raw_request_body}"
  expected_signature = hmac.new(
      webhook_secret.encode("utf-8"),
      signed_payload.encode("utf-8"),
      hashlib.sha256
  ).hexdigest()
  ```
* **Sicherheitsregeln:**
  * **Timing-Sicherheit:** Vergleich zwischen erhaltener `v1` Signatur und berechneter Signatur ausschließlich mit `hmac.compare_digest`.
  * **Replay-Schutz:** Der Zeitstempel `t` wird gegen die aktuelle Systemzeit geprüft. Weicht die Differenz um mehr als die konfigurierte Toleranz (Standard: 300 Sekunden) ab, wird die Anfrage abgewiesen.
  * **Raw Body Integrity:** Die Signaturprüfung muss exakt auf den unveränderten Bytes des HTTP-Bodys erfolgen, bevor ein JSON-Parsing stattfindet.

---

## 3. Harmonisierung mit dem VibeCore Payment-Standard

Um den nahtlosen Parallelbetrieb von Pagopar (lokal Paraguay) und Stripe (international) im VibeCore ERP zu gewährleisten, folgen beide Adapter derselben Ereignis- und Zustandshierarchie:

### 3.1 Harmonisierte Auftragszustände
* `INITIATED`: Transaktion im ERP vorgemerkt.
* `PENDING_PAYMENT`: Zahlungsziel bei Gateway erzeugt, Checkout-URL aktiv.
* `PAID`: Zahlung erfolgreich verbucht und bestätigt.
* `EXPIRED`: Zahlungsfrist abgelaufen.
* `FAILED`: Zahlung fehlgeschlagen oder vom Gateway abgelehnt.
* `CANCELLED`: Vom Händler oder Kunden storniert.

### 3.2 Standardisierte Event-Payloads für den Finance Core
Sobald eine Zahlung finalisiert wird, erzeugt der Adapter standardisierte Payloads:

#### Event: `payment.succeeded`
```json
{
  "event": "payment.succeeded",
  "gateway": "stripe",
  "order_id": "ORD-2026-0042",
  "payment_id": "pi_3N...",
  "session_id": "cs_test_...",
  "amount": 49.90,
  "currency": "USD",
  "amount_in_cents": 4990,
  "status": "PAID",
  "paid_at": "2026-10-15T22:30:00Z",
  "payment_method": "card",
  "receipt_url": "https://pay.stripe.com/receipts/...",
  "customer_email": "buyer@example.com",
  "meta": {},
  "custom_data": {}
}
```

#### Event: `payment.failed`
```json
{
  "event": "payment.failed",
  "gateway": "stripe",
  "order_id": "ORD-2026-0042",
  "payment_id": "pi_3N...",
  "session_id": "cs_test_...",
  "amount": 49.90,
  "currency": "USD",
  "status": "FAILED",
  "failure_reason": "card_declined",
  "customer_email": "buyer@example.com",
  "meta": {},
  "custom_data": {}
}
```

### 3.3 Idempotenz-Architektur gegen doppelte Zustellung
Stripe sendet Webhooks bei Netzwerkfehlern bis zu 3 Tage lang wiederholt aus.
* Jeder eingehende Webhook wird anhand der eindeutigen Stripe Event-ID (`evt_...`) sowie der PaymentIntent-/Session-ID in der lokalen SQLite-Tabelle `stripe_webhook_logs` protokolliert.
* Ist ein Webhook bereits als `PROCESSED` markiert, quittiert der Adapter den Aufruf sofort mit HTTP 200 und dem Status `already_processed`, ohne Buchungen im Core erneut anzustoßen.
* Die Auftragserstellung akzeptiert den Header `X-Idempotency-Key` und reicht diesen bei Stripe als `Idempotency-Key` durch.
