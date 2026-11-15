# Dolibarr ERP Persistent Stack (Oro Ku'i / UPA Extension)

Persistenter Docker Compose Stack fuer **Dolibarr ERP (v24.0.2)** mit **MariaDB 11**, vorkonfiguriert fuer Mengen-Tracking (Produkte, Chargen/Lots, Lager, Stücklisten/BOM, MRP-Fertigung) sowie Fakturierung, Kasse (TakePOS), Bank/Kasse, Buchhaltung und REST-API (zur Vorbereitung und Evaluierung der SIFEN-Container-Integration).

## 1. Zugangsdaten & Endpunkte

| Parameter | Wert |
|---|---|
| **Web UI URL (Lokal)** | `http://localhost:8090` |
| **Web UI URL (Tailscale / Host)** | `http://100.110.128.107:8090` |
| **TakePOS Kasse URL** | `http://localhost:8090/takepos/index.php` |
| **REST API Base URL** | `http://localhost:8090/api/index.php` |
| **REST API Explorer (Swagger)** | `http://localhost:8090/api/index.php/explorer` |
| **Admin Benutzername** | `admin` |
| **Admin Passwort** | `OroKui2026!Admin` |
| **REST API Key (`DOLAPIKEY`)** | `orokui-dolibarr-api-key-2026` |
| **MariaDB Datenbank / User** | `dolibarr` / `dolibarr` |
| **MariaDB Passwort** | `dolibarr_db_pass_2026` |

## 2. Persistenz & Volumes

Die Datenpersistenz über Container-Neustarts und Recreates hinweg wird durch drei benannte Docker Volumes sichergestellt:

- `vibecore_dolibarr_db_data` (`/var/lib/mysql`): MariaDB 11 Datenbankdateien (UTF8MB4).
- `vibecore_dolibarr_documents` (`/var/www/documents`): Dolibarr Dokumente, Belege, PDFs und `install.lock`.
- `vibecore_dolibarr_custom` (`/var/www/html/custom`): Eigene Erweiterungen und Module.

Beide Services (`dolibarr-db`, `dolibarr-web`) nutzen `restart: unless-stopped` sowie gekoppelte Healthchecks (`service_healthy`), sodass unvollständige Datenbankstarts abgefangen werden.

## 3. Aktivierte & Vorkonfigurierte Module

Über `DOLI_ENABLE_MODULES` sowie das idempotente Startup-Skript `scripts/before-starting.d/10-init-orokui-modules.php` werden folgende Standardmodule automatisch aktiviert und nach jedem Container-Neustart verifiziert:

- **Mengen-Tracking & Fertigung (Oro Ku'i)**:
  - `modProduct` & `modService` (Produkte & Dienstleistungen)
  - `modProductBatch` (Chargen / Lots / Seriennummern)
  - `modStock` & `modStockTransfer` (Lagerverwaltung & Lagertransfers, inkl. Standardlager `ALMACEN-OROKUI-01`)
  - `modBom` (Stücklisten / Bills of Materials)
  - `modMrp` & `modWorkstation` (MRP Fertigungsaufträge & Arbeitsplätze)
- **Fakturierung, Kasse & Finanzen (SIFEN-Vorbereitung)**:
  - `modSociete` (Geschäftspartner, inkl. Standard-POS-Kunde `CU-POS-0001`)
  - `modPropale`, `modCommande`, `modExpedition`, `modFacture` (Angebote, Aufträge, Versand, Kundenrechnungen)
  - `modFournisseur`, `modSupplierOrder`, `modSupplierInvoice`, `modReception` (Lieferanten, Bestellungen, Eingangsrechnungen, Wareneingang)
  - `modTakePos` (Kasse Terminal 1 vorkonfiguriert mit Lager `ALMACEN-OROKUI-01`, Kasse `CAJA-POS-PYG` und Kunde `CU-POS-0001`)
  - `modBanque` (Bank- und Kassenkonten in `PYG`: `CAJA-POS-PYG` & `BANCO-OP-PYG`)
  - `modTax`, `modAccounting`, `modMultiCurrency` (Steuern, Doppelte Buchführung, Mehrwährungen)
- **Schnittstellen**:
  - `modApi` & `modWebhook` (REST API & Webhooks für SIFEN-Adapter-Anbindung)

## 4. Betrieb & Befehle

```bash
# Stack starten
docker compose -f infra/dolibarr/docker-compose.yml up -d

# Status und Healthchecks pruefen
docker compose -f infra/dolibarr/docker-compose.yml ps

# REST API Status & Produkte abfragen
curl -fsS -H "DOLAPIKEY: orokui-dolibarr-api-key-2026" http://localhost:8090/api/index.php/status
```
