# PRD: VibeCore Migration 01 - SQLAlchemy Core Models

## Objective
Generate the foundational SQLAlchemy models for the `core` schema of our headless ERP system. The architecture MUST strictly comply with Paraguayan SIFEN (e-invoicing) and national accounting standards.

## Reference Material (Mandatory Reading)
Analyze the following files located in the `docs/reference_material/` directory before writing any code:
1. `sales_invoice_ERP_Next.json` & `item_ERPNext.json`: Use these as the structural blueprint for relational database design (document headers, document items, product master data). Ignore all UI-specific or frontend fields.
2. `SIFEN_DE_Structure.txt` (or the SIFEN Manual Técnico): Extract the mandatory fields required for Paraguayan electronic invoices (e.g., Timbrado, CDC, RUC with validation digit/DV, Punto de Expedición).
3. `account_*.xml / .csv`: Analyze the structure for the Paraguayan Chart of Accounts (Plan de Cuentas) and VAT tax rates (IVA Exenta, 5%, 10%).

## Architectural Constraints
*   **Database Engine:** PostgreSQL. All tables must be created within the `core` schema.
*   **Data Types:** Financial amounts, quantities, and exchange rates MUST be defined as `NUMERIC`.
*   **Extensibility:** EVERY model must include a `metadata` column of type `JSONB` to store unstructured, customer-specific payload data (Extension Pattern).
*   **Required Models:**
    *   `Partner` (Must include RUC, DV, Legal Name, Customer/Supplier flags)
    *   `Account` (Chart of Accounts structure)
    *   `Tax` (Tax definitions e.g., IVA 10%)
    *   `Product` (Item master data)
    *   `Document` (Invoice/Receipt header, including multi-currency fields and SIFEN requirements)
    *   `DocumentItem` (Invoice lines with tax relations and quantity)

## Task
Generate the complete Python code for these SQLAlchemy models. Ensure strict foreign key constraints and appropriate `ondelete` cascading behaviors. Place the output in the `backend/app/models/` directory.
