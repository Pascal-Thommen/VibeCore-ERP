#!/usr/bin/env php
<?php
/**
 * Idempotent bootstrap script for Dolibarr ERP (Oro Ku'i / UPA Extension).
 * Ensures required modules (Stock, MRP/BOM, Invoices, TakePOS, Bank, Accounting, REST API)
 * and baseline configurations remain enabled and ready across container restarts.
 */

if (!defined('NOLOGIN')) {
    define('NOLOGIN', '1');
}
if (!defined('NOCSRFCHECK')) {
    define('NOCSRFCHECK', '1');
}

require_once '/var/www/html/master.inc.php';
require_once DOL_DOCUMENT_ROOT . '/core/lib/admin.lib.php';
require_once DOL_DOCUMENT_ROOT . '/core/lib/security.lib.php';
require_once DOL_DOCUMENT_ROOT . '/core/lib/company.lib.php';
require_once DOL_DOCUMENT_ROOT . '/core/class/ccountry.class.php';

echo "[OROKUI-INIT] Starting idempotent module & configuration check...\n";

// 1. Ensure all required modules are activated in dependency order
$requiredModules = array(
    'User',
    'Societe',
    'Categorie',
    'Barcode',
    'Product',
    'Service',
    'ProductBatch',
    'Stock',
    'StockTransfer',
    'Bom',
    'Workstation',
    'Mrp',
    'Propale',
    'Commande',
    'Expedition',
    'Facture',
    'Fournisseur',
    'SupplierOrder',
    'SupplierInvoice',
    'Reception',
    'Tax',
    'Banque',
    'Accounting',
    'TakePos',
    'MultiCurrency',
    'Api',
    'Webhook',
    'Import',
    'Export',
);

// Ensure simple accounting (modComptabilite) is disabled so double-entry accounting (modAccounting) can be enabled
if (getDolGlobalString('MAIN_MODULE_COMPTABILITE')) {
    echo "[OROKUI-INIT] Deactivating conflicting legacy module modComptabilite... ";
    unActivateModule('modComptabilite');
    $conf->setValues($db);
    echo "OK\n";
}

foreach ($requiredModules as $modName) {
    $constName = 'MAIN_MODULE_' . strtoupper($modName);
    if (!getDolGlobalString($constName)) {
        echo "[OROKUI-INIT] Activating module mod{$modName}... ";
        $res = activateModule('mod' . $modName);
        if ($res < 0) {
            echo "WARN (code={$res})\n";
        } else {
            echo "OK\n";
        }
    }
}

// Reload conf values after module activation
$conf->setValues($db);

// 2. Company & Country (Paraguay / PYG) baseline configuration
$countryCode = getenv('DOLI_COMPANY_COUNTRYCODE') ?: 'PY';
$countryId = 0;
$country = new Ccountry($db);
if ($country->fetch(0, $countryCode) > 0) {
    $countryId = (int) $country->id;
    $countryVal = $country->id . ':' . $country->code . ':' . $country->label;
    dolibarr_set_const($db, 'MAIN_INFO_SOCIETE_COUNTRY', $countryVal, 'chaine', 0, '', $conf->entity);
}

$companyName = getenv('DOLI_COMPANY_NAME') ?: "Oro Ku'i (UPA Extension)";
dolibarr_set_const($db, 'MAIN_INFO_SOCIETE_NOM', $companyName, 'chaine', 0, '', $conf->entity);
if (!getDolGlobalString('MAIN_MONNAIE')) {
    dolibarr_set_const($db, 'MAIN_MONNAIE', 'PYG', 'chaine', 0, 'Default currency (Guarani)', $conf->entity);
} else {
    dolibarr_set_const($db, 'MAIN_MONNAIE', 'PYG', 'chaine', 0, 'Default currency (Guarani)', $conf->entity);
}

// 3. REST API readiness (enable login endpoint + configure deterministic admin API key)
dolibarr_set_const($db, 'API_ENABLE_LOGIN_API', '1', 'chaine', 0, 'Allow REST API login endpoint for integration tests', 0);
dolibarr_set_const($db, 'API_ENABLE_LOGIN_API', '1', 'chaine', 0, 'Allow REST API login endpoint for integration tests', $conf->entity);

$apiTempDir = DOL_DATA_ROOT . '/api/temp';
if (!is_dir($apiTempDir)) {
    @mkdir($apiTempDir, 0775, true);
}
@chown($apiTempDir, 'www-data');
@chgrp($apiTempDir, 'www-data');

$adminLogin = getenv('DOLI_ADMIN_LOGIN') ?: 'admin';
$apiKeyPlain = getenv('DOLI_API_KEY') ?: 'orokui-dolibarr-api-key-2026';
$apiKeyEncrypted = dolEncrypt($apiKeyPlain, '', '', 'dolibarr');

$sqlUser = "SELECT rowid, api_key FROM " . MAIN_DB_PREFIX . "user WHERE login = '" . $db->escape($adminLogin) . "' LIMIT 1";
$resUser = $db->query($sqlUser);
$adminUserId = 1;
if ($resUser && $db->num_rows($resUser) > 0) {
    $objUser = $db->fetch_object($resUser);
    $adminUserId = (int) $objUser->rowid;
    if (empty($objUser->api_key)) {
        $sqlUpdKey = "UPDATE " . MAIN_DB_PREFIX . "user SET api_key = '" . $db->escape($apiKeyEncrypted) . "' WHERE rowid = " . $adminUserId;
        $db->query($sqlUpdKey);
        echo "[OROKUI-INIT] Configured API key for admin user '{$adminLogin}'.\n";
    }
}

// 4. Default Warehouse for Stock & MRP (Mengentracking Oro Ku'i)
$warehouseRef = 'ALMACEN-OROKUI-01';
$warehouseId = 0;
$sqlWh = "SELECT rowid FROM " . MAIN_DB_PREFIX . "entrepot WHERE ref = '" . $db->escape($warehouseRef) . "' AND entity = " . ((int) $conf->entity) . " LIMIT 1";
$resWh = $db->query($sqlWh);
if ($resWh && $db->num_rows($resWh) > 0) {
    $warehouseId = (int) $db->fetch_object($resWh)->rowid;
} else {
    $sqlInsWh = "INSERT INTO " . MAIN_DB_PREFIX . "entrepot (ref, datec, entity, description, lieu, town, fk_pays, statut, fk_user_author) VALUES ("
        . "'" . $db->escape($warehouseRef) . "', "
        . "'" . $db->idate(dol_now()) . "', "
        . ((int) $conf->entity) . ", "
        . "'Hauptlager Oro Ku''i fuer Rohstoffe, Zwischenprodukte und Fertigwaren (MRP & POS)', "
        . "'Zentrallager Oro Ku''i', "
        . "'Asuncion', "
        . $countryId . ", "
        . "1, "
        . $adminUserId . ")";
    if ($db->query($sqlInsWh)) {
        $warehouseId = (int) $db->last_insert_id(MAIN_DB_PREFIX . 'entrepot');
        echo "[OROKUI-INIT] Created default warehouse '{$warehouseRef}' (id={$warehouseId}).\n";
    }
}

// 5. Default Cash & Bank Accounts in PYG
$cashRef = 'CAJA-POS-PYG';
$cashAccountId = 0;
$sqlCash = "SELECT rowid FROM " . MAIN_DB_PREFIX . "bank_account WHERE ref = '" . $db->escape($cashRef) . "' AND entity = " . ((int) $conf->entity) . " LIMIT 1";
$resCash = $db->query($sqlCash);
if ($resCash && $db->num_rows($resCash) > 0) {
    $cashAccountId = (int) $db->fetch_object($resCash)->rowid;
} else {
    $sqlInsCash = "INSERT INTO " . MAIN_DB_PREFIX . "bank_account (datec, ref, label, entity, fk_user_author, fk_pays, courant, clos, rappro, currency_code, account_number) VALUES ("
        . "'" . $db->idate(dol_now()) . "', "
        . "'" . $db->escape($cashRef) . "', "
        . "'Kasse TakePOS Oro Ku''i (PYG)', "
        . ((int) $conf->entity) . ", "
        . $adminUserId . ", "
        . $countryId . ", "
        . "2, 0, 0, 'PYG', '1010101')";
    if ($db->query($sqlInsCash)) {
        $cashAccountId = (int) $db->last_insert_id(MAIN_DB_PREFIX . 'bank_account');
        echo "[OROKUI-INIT] Created default POS cash account '{$cashRef}' (id={$cashAccountId}).\n";
    }
}

$bankRef = 'BANCO-OP-PYG';
$bankAccountId = 0;
$sqlBank = "SELECT rowid FROM " . MAIN_DB_PREFIX . "bank_account WHERE ref = '" . $db->escape($bankRef) . "' AND entity = " . ((int) $conf->entity) . " LIMIT 1";
$resBank = $db->query($sqlBank);
if ($resBank && $db->num_rows($resBank) > 0) {
    $bankAccountId = (int) $db->fetch_object($resBank)->rowid;
} else {
    $sqlInsBank = "INSERT INTO " . MAIN_DB_PREFIX . "bank_account (datec, ref, label, entity, fk_user_author, fk_pays, courant, clos, rappro, currency_code, account_number) VALUES ("
        . "'" . $db->idate(dol_now()) . "', "
        . "'" . $db->escape($bankRef) . "', "
        . "'Operatives Bankkonto Oro Ku''i (PYG)', "
        . ((int) $conf->entity) . ", "
        . $adminUserId . ", "
        . $countryId . ", "
        . "1, 0, 1, 'PYG', '1010201')";
    if ($db->query($sqlInsBank)) {
        $bankAccountId = (int) $db->last_insert_id(MAIN_DB_PREFIX . 'bank_account');
        echo "[OROKUI-INIT] Created default bank account '{$bankRef}' (id={$bankAccountId}).\n";
    }
}

// 6. Default Generic Customer for TakePOS & Invoicing tests
$posCustomerCode = 'CU-POS-0001';
$posCustomerId = 0;
$sqlCust = "SELECT rowid FROM " . MAIN_DB_PREFIX . "societe WHERE code_client = '" . $db->escape($posCustomerCode) . "' AND entity = " . ((int) $conf->entity) . " LIMIT 1";
$resCust = $db->query($sqlCust);
if ($resCust && $db->num_rows($resCust) > 0) {
    $posCustomerId = (int) $db->fetch_object($resCust)->rowid;
} else {
    $sqlInsCust = "INSERT INTO " . MAIN_DB_PREFIX . "societe (nom, name_alias, entity, statut, status, code_client, client, fournisseur, fk_pays, datec, fk_user_creat) VALUES ("
        . "'Consumidor Final POS (Oro Ku''i)', "
        . "'Laufkunde Kasse', "
        . ((int) $conf->entity) . ", "
        . "0, 1, "
        . "'" . $db->escape($posCustomerCode) . "', "
        . "1, 0, "
        . $countryId . ", "
        . "'" . $db->idate(dol_now()) . "', "
        . $adminUserId . ")";
    if ($db->query($sqlInsCust)) {
        $posCustomerId = (int) $db->last_insert_id(MAIN_DB_PREFIX . 'societe');
        echo "[OROKUI-INIT] Created default POS customer '{$posCustomerCode}' (id={$posCustomerId}).\n";
    }
}

// 7. Configure TakePOS Terminal 1 defaults
dolibarr_set_const($db, 'TAKEPOS_NUM_TERMINALS', '1', 'chaine', 0, '', $conf->entity);
dolibarr_set_const($db, 'TAKEPOS_TERMINAL_NAME_1', "Kasse 1 - Oro Ku'i", 'chaine', 0, '', $conf->entity);
if ($posCustomerId > 0) {
    dolibarr_set_const($db, 'CASHDESK_ID_THIRDPARTY1', (string) $posCustomerId, 'chaine', 0, '', $conf->entity);
}
if ($cashAccountId > 0) {
    dolibarr_set_const($db, 'CASHDESK_ID_BANKACCOUNT_CASH1', (string) $cashAccountId, 'chaine', 0, '', $conf->entity);
}
if ($bankAccountId > 0) {
    dolibarr_set_const($db, 'CASHDESK_ID_BANKACCOUNT_CB1', (string) $bankAccountId, 'chaine', 0, '', $conf->entity);
}
if ($warehouseId > 0) {
    dolibarr_set_const($db, 'CASHDESK_ID_WAREHOUSE1', (string) $warehouseId, 'chaine', 0, '', $conf->entity);
    dolibarr_set_const($db, 'MAIN_DEFAULT_WAREHOUSE', (string) $warehouseId, 'chaine', 0, '', $conf->entity);
}

chown_r('/var/www/documents');

function chown_r($path) {
    if (!file_exists($path)) {
        return;
    }
    @chown($path, 'www-data');
    @chgrp($path, 'www-data');
}

echo "[OROKUI-INIT] Bootstrap completed successfully.\n";
