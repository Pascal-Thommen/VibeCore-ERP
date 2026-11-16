# Dolibarr ERP MCP Server (Oro Ku'i / UPA Extension)

Lokaler Model Context Protocol (MCP) Server auf Basis von **FastMCP** (`mcp`), fest verdrahtet mit der lokalen Dolibarr-Instanz (`http://localhost:8090/api/index.php`) und dem API-Schluessel `orokui-dolibarr-api-key-2026`.

## 1. Vorkonfigurierte Verbindungsparameter

| Parameter | Standardwert | Umgebungsvariable |
|---|---|---|
| **REST API URL** | `http://localhost:8090/api/index.php` | `DOLIBARR_API_URL` |
| **API Key (`DOLAPIKEY`)** | `orokui-dolibarr-api-key-2026` | `DOLIBARR_API_KEY` |
| **Timeout (Sekunden)** | `10.0` | `DOLIBARR_API_TIMEOUT` |
| **SSE / HTTP Port (Container)** | `8091` (`http://localhost:8091/sse`, `/health`) | `DOLI_MCP_PORT` |

## 2. Bereitgestellte MCP-Tools

- `dolibarr_status`: Verbindungs- und Versionsprüfung der Dolibarr REST-API.
- `dolibarr_erp_summary`: Vollständige Kennzahlen- und Saldenübersicht aller aktiven Module in `PYG`.
- `list_thirdparties`, `get_thirdparty`, `create_thirdparty`: Abfrage und Anlage von Kunden und Lieferanten (inkl. RUC).
- `list_contacts`: Abfrage von Kontaktpersonen (`socpeople`).
- `list_products`, `get_product_stock`: Produktkatalog, Lagerbestände je Lagerort sowie Chargen-/Lot-Bestände (`tobatch`).
- `list_warehouses`, `list_stock_movements`, `create_stock_movement`: Lagerorte und reale Bestandsbewegungen.
- `list_proposals`, `list_orders`: Angebote (`Propal`) und Kundenaufträge (`Commande`).
- `list_invoices`, `get_invoice`: Kundenrechnungen und TakePOS-Kassenbelege inklusive Zahlungsstatus und Positionen.
- `list_supplier_documents`: Lieferantenbestellungen und Eingangsrechnungen.
- `list_cash_and_bank_ledger`: Kassenbuch (`CAJA-POS-PYG`) und Bankkonto (`BANCO-OP-PYG`) inkl. Einzelbuchungen.
- `list_boms_and_manufacturing_orders`: Stücklisten (BOM) und MRP-Fertigungsaufträge.

## 3. Konfiguration für Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "dolibarr-orokui": {
      "command": "/home/pasc/.venv-vibecore/bin/dolibarr-mcp",
      "args": ["--transport", "stdio"],
      "env": {
        "DOLIBARR_API_URL": "http://localhost:8090/api/index.php",
        "DOLIBARR_API_KEY": "orokui-dolibarr-api-key-2026",
        "DOLIBARR_API_TIMEOUT": "10.0"
      }
    }
  }
}
```

## 4. Konfiguration für Cursor (`.cursor/mcp.json`)

### Option A: Lokaler Prozess (`stdio`)
```json
{
  "mcpServers": {
    "dolibarr-orokui": {
      "command": "/home/pasc/.venv-vibecore/bin/dolibarr-mcp",
      "args": ["--transport", "stdio"],
      "env": {
        "DOLIBARR_API_URL": "http://localhost:8090/api/index.php",
        "DOLIBARR_API_KEY": "orokui-dolibarr-api-key-2026",
        "DOLIBARR_API_TIMEOUT": "10.0"
      }
    }
  }
}
```

### Option B: Laufender SSE-Container (`http://localhost:8091/sse`)
```json
{
  "mcpServers": {
    "dolibarr-orokui-sse": {
      "url": "http://localhost:8091/sse"
    }
  }
}
```
