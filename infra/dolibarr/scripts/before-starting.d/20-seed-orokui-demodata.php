#!/usr/bin/env php
<?php
/**
 * Idempotent Demo Data Seeder for Dolibarr ERP (Oro Ku'i / UPA Extension).
 *
 * Populates realistic Paraguayan (PYG) master data and document chains across all enabled modules:
 * - Warehouses (Hauptlager, Produktionslager, POS-Verkaufslager)
 * - Thirdparties (B2B/POS Customers & Paraguayan Suppliers with RUC)
 * - Contacts (Ansprechpartner fuer Einkauf, Vertrieb, Buchhaltung, Logistik)
 * - Products & Services with real Stock Movements & Batch/Lot Tracking (Mengentracking)
 * - BOM & MRP Manufacturing Order (Stueckliste & Fertigungsauftrag)
 * - Commercial Proposals (Angebote)
 * - Customer Sales Orders (Kundenauftraege)
 * - Customer Invoices & TakePOS Receipts (Kundenrechnungen & Kassenbelege)
 * - Supplier Orders & Supplier Invoices (Lieferantenbestellungen & Eingangsrechnungen)
 * - Cash Desk (CAJA-POS-PYG) & Operational Bank (BANCO-OP-PYG) Ledger Bookings
 */

if (!defined('NOLOGIN')) {
    define('NOLOGIN', '1');
}
if (!defined('NOCSRFCHECK')) {
    define('NOCSRFCHECK', '1');
}

require_once '/var/www/html/master.inc.php';
require_once DOL_DOCUMENT_ROOT . '/user/class/user.class.php';
require_once DOL_DOCUMENT_ROOT . '/core/class/ccountry.class.php';
require_once DOL_DOCUMENT_ROOT . '/societe/class/societe.class.php';
require_once DOL_DOCUMENT_ROOT . '/contact/class/contact.class.php';
require_once DOL_DOCUMENT_ROOT . '/product/class/product.class.php';
require_once DOL_DOCUMENT_ROOT . '/product/stock/class/entrepot.class.php';
require_once DOL_DOCUMENT_ROOT . '/comm/propal/class/propal.class.php';
require_once DOL_DOCUMENT_ROOT . '/commande/class/commande.class.php';
require_once DOL_DOCUMENT_ROOT . '/compta/facture/class/facture.class.php';
require_once DOL_DOCUMENT_ROOT . '/compta/paiement/class/paiement.class.php';
require_once DOL_DOCUMENT_ROOT . '/fourn/class/fournisseur.product.class.php';
require_once DOL_DOCUMENT_ROOT . '/fourn/class/fournisseur.commande.class.php';
require_once DOL_DOCUMENT_ROOT . '/fourn/class/fournisseur.facture.class.php';
require_once DOL_DOCUMENT_ROOT . '/fourn/class/paiementfourn.class.php';
require_once DOL_DOCUMENT_ROOT . '/compta/bank/class/account.class.php';
require_once DOL_DOCUMENT_ROOT . '/bom/class/bom.class.php';
require_once DOL_DOCUMENT_ROOT . '/mrp/class/mo.class.php';

echo "[OROKUI-SEED] Starting idempotent demo data verification & seeding...\n";

$user = new User($db);
if ($user->fetch(1) <= 0) {
    $resU = $db->query("SELECT rowid FROM " . MAIN_DB_PREFIX . "user ORDER BY rowid ASC LIMIT 1");
    if ($resU && $db->num_rows($resU) > 0) {
        $user->fetch((int) $db->fetch_object($resU)->rowid);
    }
}
$user->getrights();

$countryId = 0;
$country = new Ccountry($db);
if ($country->fetch(0, 'PY') > 0) {
    $countryId = (int) $country->id;
}

$now = dol_now();

// Helper functions for idempotent lookups
function findIdByColumn($db, $table, $col, $val, $entity = 1) {
    $sql = "SELECT rowid FROM " . MAIN_DB_PREFIX . $table
         . " WHERE " . $col . " = '" . $db->escape($val) . "'";
    if ($entity !== null) {
        $sql .= " AND entity = " . ((int) $entity);
    }
    $sql .= " LIMIT 1";
    $res = $db->query($sql);
    if ($res && $db->num_rows($res) > 0) {
        return (int) $db->fetch_object($res)->rowid;
    }
    return 0;
}

function getPaymentTypeId($db, $code) {
    $sql = "SELECT id FROM " . MAIN_DB_PREFIX . "c_paiement WHERE code = '" . $db->escape($code) . "' LIMIT 1";
    $res = $db->query($sql);
    if ($res && $db->num_rows($res) > 0) {
        return (int) $db->fetch_object($res)->id;
    }
    return 4; // Fallback LIQ
}

$payIdVir = getPaymentTypeId($db, 'VIR');
$payIdLiq = getPaymentTypeId($db, 'LIQ');
$payIdCb  = getPaymentTypeId($db, 'CB');

// ============================================================================
// 1. WAREHOUSES (Lager)
// ============================================================================
$warehousesSpec = array(
    array(
        'ref' => 'ALMACEN-OROKUI-01',
        'lieu' => "Zentrallager Oro Ku'i",
        'description' => "Hauptlager Oro Ku'i fuer Rohstoffe, Zwischenprodukte und Fertigwaren (MRP & POS)",
        'town' => 'Asuncion',
        'address' => 'Av. Artigas 1540, Zona Industrial',
        'zip' => '1209',
    ),
    array(
        'ref' => 'ALMACEN-PROD-02',
        'lieu' => "Produktionslager & Reifekammer Oro Ku'i",
        'description' => 'Produktionslager fuer Teigverarbeitung, Kaesereifung und Chargenfertigung (MRP)',
        'town' => 'Asuncion',
        'address' => 'Av. Artigas 1542, Planta MRP',
        'zip' => '1209',
    ),
    array(
        'ref' => 'ALMACEN-TIENDA-03',
        'lieu' => "Verkaufslager & POS Filiale Villa Morra",
        'description' => 'Kassenlager fuer Direktverkauf TakePOS und Kuehltheke Villa Morra',
        'town' => 'Asuncion',
        'address' => 'Calle Senador Long 720, Villa Morra',
        'zip' => '1408',
    ),
);

$warehouseIds = array();
foreach ($warehousesSpec as $wSpec) {
    $wId = findIdByColumn($db, 'entrepot', 'ref', $wSpec['ref']);
    if ($wId <= 0) {
        $wh = new Entrepot($db);
        $wh->ref = $wSpec['ref'];
        $wh->label = $wSpec['ref'];
        $wh->lieu = $wSpec['lieu'];
        $wh->description = $wSpec['description'];
        $wh->town = $wSpec['town'];
        $wh->address = $wSpec['address'];
        $wh->zip = $wSpec['zip'];
        $wh-> country_id = $countryId;
        $wh->statut = 1;
        $createdId = $wh->create($user);
        if ($createdId > 0) {
            $wId = (int) $createdId;
            echo "[OROKUI-SEED] Created warehouse '{$wSpec['ref']}' (id={$wId}).\n";
        }
    }
    $warehouseIds[$wSpec['ref']] = $wId;
}

// ============================================================================
// 2. THIRDPARTIES (Kunden & Lieferanten)
// ============================================================================
$thirdpartiesSpec = array(
    'CU-POS-0001' => array(
        'nom' => "Consumidor Final POS (Oro Ku'i)",
        'name_alias' => 'Laufkunde Kasse TakePOS',
        'code_client' => 'CU-POS-0001',
        'code_fournisseur' => '',
        'client' => 1,
        'fournisseur' => 0,
        'idprof1' => '44444401-7',
        'email' => 'pos@orokui.com.py',
        'phone' => '+595 21 600 100',
        'address' => 'Calle Senador Long 720',
        'town' => 'Asuncion',
        'zip' => '1408',
    ),
    'CU-OROKUI-0002' => array(
        'nom' => 'Supermercados Casa Rica S.A.',
        'name_alias' => 'Casa Rica Retail Gourmet',
        'code_client' => 'CU-OROKUI-0002',
        'code_fournisseur' => '',
        'client' => 1,
        'fournisseur' => 0,
        'idprof1' => '80012345-6',
        'email' => 'compras@casarica.com.py',
        'phone' => '+595 21 615 200',
        'address' => 'Av. Espana 2210 c/ America',
        'town' => 'Asuncion',
        'zip' => '1404',
    ),
    'CU-OROKUI-0003' => array(
        'nom' => 'Cafe & Bistro Karu Pora S.R.L.',
        'name_alias' => 'Karu Pora Gastronomie',
        'code_client' => 'CU-OROKUI-0003',
        'code_fournisseur' => '',
        'client' => 1,
        'fournisseur' => 0,
        'idprof1' => '80054321-0',
        'email' => 'administracion@karupora.com.py',
        'phone' => '+595 21 662 340',
        'address' => 'Calle Pacheco 4185, Recoleta',
        'town' => 'Asuncion',
        'zip' => '1406',
    ),
    'CU-OROKUI-0004' => array(
        'nom' => 'Hotel Guarani Esplendor S.A.',
        'name_alias' => 'Hotel Guarani Catering & Eventos',
        'code_client' => 'CU-OROKUI-0004',
        'code_fournisseur' => '',
        'client' => 1,
        'fournisseur' => 0,
        'idprof1' => '80067890-1',
        'email' => 'abastecimiento@hotelguarani.com.py',
        'phone' => '+595 21 452 099',
        'address' => 'Oliva esq. Independencia Nacional',
        'town' => 'Asuncion',
        'zip' => '1101',
    ),
    'CU-OROKUI-0005' => array(
        'nom' => 'Distribuidora Del Este S.A.',
        'name_alias' => 'Grosshandel Alto Parana',
        'code_client' => 'CU-OROKUI-0005',
        'code_fournisseur' => '',
        'client' => 1,
        'fournisseur' => 0,
        'idprof1' => '80098765-4',
        'email' => 'pedidos@distdeleste.com.py',
        'phone' => '+595 61 570 800',
        'address' => 'Ruta PY02 Km 4, Parque Logistico',
        'town' => 'Ciudad del Este',
        'zip' => '7000',
    ),
    'SU-OROKUI-0001' => array(
        'nom' => 'Cooperativa Agricola San Pedro Ltda.',
        'name_alias' => 'Lieferant Maniok & Agrarrohstoffe',
        'code_client' => '',
        'code_fournisseur' => 'SU-OROKUI-0001',
        'client' => 0,
        'fournisseur' => 1,
        'idprof1' => '80011223-4',
        'email' => 'ventas@coopsanpedro.org.py',
        'phone' => '+595 342 222 150',
        'address' => 'Ruta PY03 Km 245, Zona Agricola',
        'town' => 'San Pedro de Ycuamandyyu',
        'zip' => '0201',
    ),
    'SU-OROKUI-0002' => array(
        'nom' => 'Envases & Empaques Paraguay S.A.',
        'name_alias' => 'Lieferant Verpackung & Etiketten',
        'code_client' => '',
        'code_fournisseur' => 'SU-OROKUI-0002',
        'client' => 0,
        'fournisseur' => 1,
        'idprof1' => '80033445-5',
        'email' => 'comercial@envasespy.com.py',
        'phone' => '+595 21 645 910',
        'address' => 'Autopista Silvio Pettirossi Km 14',
        'town' => 'Luque',
        'zip' => '2060',
    ),
    'SU-OROKUI-0003' => array(
        'nom' => 'Agroindustrial Itapua S.A.',
        'name_alias' => 'Lieferant Kaese, Milch & Speisestaerke',
        'code_client' => '',
        'code_fournisseur' => 'SU-OROKUI-0003',
        'client' => 0,
        'fournisseur' => 1,
        'idprof1' => '80055667-8',
        'email' => 'despacho@agroitapua.com.py',
        'phone' => '+595 71 204 500',
        'address' => 'Ruta PY06 Km 12, Sector Industrial',
        'town' => 'Encarnacion',
        'zip' => '6000',
    ),
);

$thirdpartyIds = array();
foreach ($thirdpartiesSpec as $key => $tpSpec) {
    $col = !empty($tpSpec['code_client']) ? 'code_client' : 'code_fournisseur';
    $val = !empty($tpSpec['code_client']) ? $tpSpec['code_client'] : $tpSpec['code_fournisseur'];
    $tpId = findIdByColumn($db, 'societe', $col, $val);
    if ($tpId <= 0) {
        $soc = new Societe($db);
        $soc->name = $tpSpec['nom'];
        $soc->nom = $tpSpec['nom'];
        $soc->name_alias = $tpSpec['name_alias'];
        $soc->client = $tpSpec['client'];
        $soc->fournisseur = $tpSpec['fournisseur'];
        $soc->code_client = $tpSpec['code_client'];
        $soc->code_fournisseur = $tpSpec['code_fournisseur'];
        $soc->idprof1 = $tpSpec['idprof1'];
        $soc->tva_intra = $tpSpec['idprof1'];
        $soc->email = $tpSpec['email'];
        $soc->phone = $tpSpec['phone'];
        $soc->address = $tpSpec['address'];
        $soc->town = $tpSpec['town'];
        $soc->zip = $tpSpec['zip'];
        $soc->country_id = $countryId;
        $soc->status = 1;
        $soc->statut = 1;
        $soc->currency_code = 'PYG';
        $createdId = $soc->create($user);
        if ($createdId > 0) {
            $tpId = (int) $createdId;
            echo "[OROKUI-SEED] Created thirdparty '{$tpSpec['nom']}' (id={$tpId}).\n";
        }
    } else {
        // Ensure RUC and address metadata are enriched on existing record (e.g. CU-POS-0001)
        $sqlUpdTp = "UPDATE " . MAIN_DB_PREFIX . "societe SET "
            . "idprof1 = '" . $db->escape($tpSpec['idprof1']) . "', "
            . "email = '" . $db->escape($tpSpec['email']) . "', "
            . "phone = '" . $db->escape($tpSpec['phone']) . "', "
            . "address = '" . $db->escape($tpSpec['address']) . "', "
            . "town = '" . $db->escape($tpSpec['town']) . "', "
            . "zip = '" . $db->escape($tpSpec['zip']) . "' "
            . "WHERE rowid = " . $tpId . " AND (idprof1 IS NULL OR idprof1 = '')";
        $db->query($sqlUpdTp);
    }
    $thirdpartyIds[$key] = $tpId;
}

// ============================================================================
// 3. CONTACTS / ADDRESSES (Ansprechpartner)
// ============================================================================
$contactsSpec = array(
    array(
        'tp_key' => 'CU-OROKUI-0002',
        'firstname' => 'Maria Fernanda',
        'lastname' => 'Benitez',
        'poste' => 'Leitung Frische-Einkauf (Jefa de Compras)',
        'email' => 'mbenitez@casarica.com.py',
        'phone_pro' => '+595 21 615 211',
        'town' => 'Asuncion',
    ),
    array(
        'tp_key' => 'CU-OROKUI-0003',
        'firstname' => 'Rodrigo',
        'lastname' => 'Villalba',
        'poste' => 'Geschäftsführung & Kuechenleitung',
        'email' => 'rvillalba@karupora.com.py',
        'phone_pro' => '+595 21 662 345',
        'town' => 'Asuncion',
    ),
    array(
        'tp_key' => 'CU-OROKUI-0004',
        'firstname' => 'Lucia',
        'lastname' => 'Duarte',
        'poste' => 'Food & Beverage Managerin',
        'email' => 'lduarte@hotelguarani.com.py',
        'phone_pro' => '+595 21 452 110',
        'town' => 'Asuncion',
    ),
    array(
        'tp_key' => 'CU-OROKUI-0005',
        'firstname' => 'Carlos Alberto',
        'lastname' => 'Gimenez',
        'poste' => 'Leiter Logistik & Distribution',
        'email' => 'cgimenez@distdeleste.com.py',
        'phone_pro' => '+595 61 570 812',
        'town' => 'Ciudad del Este',
    ),
    array(
        'tp_key' => 'SU-OROKUI-0001',
        'firstname' => 'Hector',
        'lastname' => 'Rojas',
        'poste' => 'Koordinator Rohstoffvertrieb & Qualitaet',
        'email' => 'hrojas@coopsanpedro.org.py',
        'phone_pro' => '+595 342 222 155',
        'town' => 'San Pedro de Ycuamandyyu',
    ),
    array(
        'tp_key' => 'SU-OROKUI-0002',
        'firstname' => 'Sofia',
        'lastname' => 'Galeano',
        'poste' => 'Key Account Managerin Lebensmittelverpackung',
        'email' => 'sgaleano@envasespy.com.py',
        'phone_pro' => '+595 21 645 922',
        'town' => 'Luque',
    ),
);

foreach ($contactsSpec as $cSpec) {
    $existingCId = findIdByColumn($db, 'socpeople', 'email', $cSpec['email']);
    if ($existingCId <= 0 && !empty($thirdpartyIds[$cSpec['tp_key']])) {
        $ct = new Contact($db);
        $ct->socid = $thirdpartyIds[$cSpec['tp_key']];
        $ct->firstname = $cSpec['firstname'];
        $ct->lastname = $cSpec['lastname'];
        $ct->poste = $cSpec['poste'];
        $ct->email = $cSpec['email'];
        $ct->phone_pro = $cSpec['phone_pro'];
        $ct->town = $cSpec['town'];
        $ct->country_id = $countryId;
        $ct->statut = 1;
        $cId = $ct->create($user);
        if ($cId > 0) {
            echo "[OROKUI-SEED] Created contact '{$cSpec['firstname']} {$cSpec['lastname']}' (id={$cId}).\n";
        }
    }
}

// ============================================================================
// 4. PRODUCTS & SERVICES + REAL STOCK & BATCH/LOT TRACKING
// ============================================================================
$productsSpec = array(
    'OROKUI-MENGEN-01' => array(
        'ref' => 'OROKUI-MENGEN-01',
        'label' => 'Oro Kui Rohmaterial Charge A (Mengentracking)',
        'description' => 'Chargenpflichtiges Basis-Rohmaterial fuer Rueckverfolgbarkeit und Produktionspruefung (Oro Ku\'i)',
        'type' => 0,
        'price' => 25000,
        'cost_price' => 15000,
        'tva_tx' => 5,
        'tobatch' => 1,
        'seuil_stock_alerte' => 50,
        'desiredstock' => 500,
        'barcode' => '7840001000011',
    ),
    'OROKUI-RAW-01' => array(
        'ref' => 'OROKUI-RAW-01',
        'label' => 'Almidon de Mandioca Premium (Sack 25 kg)',
        'description' => 'Paraguayische Maniokstaerke erster Güteklasse aus San Pedro fuer Chipa und Mbeju',
        'type' => 0,
        'price' => 125000,
        'cost_price' => 85000,
        'tva_tx' => 5,
        'tobatch' => 0,
        'seuil_stock_alerte' => 20,
        'desiredstock' => 120,
        'barcode' => '7840001000028',
    ),
    'OROKUI-RAW-02' => array(
        'ref' => 'OROKUI-RAW-02',
        'label' => 'Queso Paraguay Estacionado (Laib 5 kg)',
        'description' => 'Gereifter Paraguay-Kaese mit Chargen- und Mindesthaltbarkeits-Tracking',
        'type' => 0,
        'price' => 185000,
        'cost_price' => 135000,
        'tva_tx' => 5,
        'tobatch' => 1,
        'seuil_stock_alerte' => 15,
        'desiredstock' => 80,
        'barcode' => '7840001000035',
    ),
    'OROKUI-RAW-03' => array(
        'ref' => 'OROKUI-RAW-03',
        'label' => "Empaque Termosellado Oro Ku'i (Rolle 1000 Stk)",
        'description' => 'Bedruckte Lebensmittel-Schutzfolienrolle mit Chargenetikett fuer Fertigpackungen',
        'type' => 0,
        'price' => 95000,
        'cost_price' => 62000,
        'tva_tx' => 10,
        'tobatch' => 0,
        'seuil_stock_alerte' => 10,
        'desiredstock' => 50,
        'barcode' => '7840001000042',
    ),
    'OROKUI-FIN-01' => array(
        'ref' => 'OROKUI-FIN-01',
        'label' => "Chipa Tradicional Oro Ku'i (Packung 12 Stk)",
        'description' => 'Traditionelle Chipa aus Maniokstaerke und Queso Paraguay, verkaufsfertig fuer Einzelhandel & POS',
        'type' => 0,
        'price' => 35000,
        'cost_price' => 18000,
        'tva_tx' => 10,
        'tobatch' => 0,
        'seuil_stock_alerte' => 60,
        'desiredstock' => 500,
        'barcode' => '7840001000059',
    ),
    'OROKUI-FIN-02' => array(
        'ref' => 'OROKUI-FIN-02',
        'label' => 'Mbeju Artesanal Pre-Cocido (Packung 6 Stk)',
        'description' => 'Handwerklicher Mbeju aus Maniokstaerke und Kaese fuer Gastronomie, Hotels und Kasse',
        'type' => 0,
        'price' => 42000,
        'cost_price' => 21000,
        'tva_tx' => 10,
        'tobatch' => 0,
        'seuil_stock_alerte' => 40,
        'desiredstock' => 300,
        'barcode' => '7840001000066',
    ),
    'OROKUI-FIN-03' => array(
        'ref' => 'OROKUI-FIN-03',
        'label' => 'Sopa Paraguaya Casera (Tray 1 kg)',
        'description' => 'Traditioneller Mais-Kaese-Auflauf im 1-kg-Frischetray fuer Feinkost und Catering',
        'type' => 0,
        'price' => 48000,
        'cost_price' => 24000,
        'tva_tx' => 10,
        'tobatch' => 0,
        'seuil_stock_alerte' => 30,
        'desiredstock' => 200,
        'barcode' => '7840001000073',
    ),
    'OROKUI-FIN-04' => array(
        'ref' => 'OROKUI-FIN-04',
        'label' => "Cocido Quemado Soluble Oro Ku'i (Dose 250g)",
        'description' => 'Geröstetes Mate-Karamellpulver fuer traditionellen Cocido in Gastronomie und Haushalt',
        'type' => 0,
        'price' => 28000,
        'cost_price' => 14000,
        'tva_tx' => 10,
        'tobatch' => 0,
        'seuil_stock_alerte' => 40,
        'desiredstock' => 350,
        'barcode' => '7840001000080',
    ),
    'OROKUI-SRV-01' => array(
        'ref' => 'OROKUI-SRV-01',
        'label' => 'Liefer- & Kuehlkettenlogistik Asuncion (Pauschale)',
        'description' => 'Temperaturgefuehrte Zustellung im Grossraum Asuncion (Gran Asuncion)',
        'type' => 1,
        'price' => 75000,
        'cost_price' => 35000,
        'tva_tx' => 10,
        'tobatch' => 0,
        'seuil_stock_alerte' => 0,
        'desiredstock' => 0,
        'barcode' => '',
    ),
);

$productIds = array();
foreach ($productsSpec as $pKey => $pSpec) {
    $pId = findIdByColumn($db, 'product', 'ref', $pSpec['ref']);
    if ($pId <= 0) {
        $prod = new Product($db);
        $prod->ref = $pSpec['ref'];
        $prod->label = $pSpec['label'];
        $prod->description = $pSpec['description'];
        $prod->type = $pSpec['type'];
        $prod->status = 1;
        $prod->status_buy = 1;
        $prod->price = $pSpec['price'];
        $prod->price_base_type = 'HT';
        $prod->tva_tx = $pSpec['tva_tx'];
        $prod->cost_price = $pSpec['cost_price'];
        $prod->pmp = $pSpec['cost_price'];
        $prod->status_batch = $pSpec['tobatch'];
        $prod->seuil_stock_alerte = $pSpec['seuil_stock_alerte'];
        $prod->desiredstock = $pSpec['desiredstock'];
        $prod->fk_default_warehouse = $warehouseIds['ALMACEN-OROKUI-01'];
        $createdId = $prod->create($user);
        if ($createdId > 0) {
            $pId = (int) $createdId;
            $prod->updatePrice($pSpec['price'], 'HT', $user, $pSpec['tva_tx']);
            echo "[OROKUI-SEED] Created product '{$pSpec['ref']}' (id={$pId}).\n";
        }
    } else {
        // Ensure existing product (e.g. OROKUI-MENGEN-01) has complete cost/alert/warehouse settings
        $sqlUpdP = "UPDATE " . MAIN_DB_PREFIX . "product SET "
            . "cost_price = " . ((float) $pSpec['cost_price']) . ", "
            . "pmp = CASE WHEN pmp IS NULL OR pmp = 0 THEN " . ((float) $pSpec['cost_price']) . " ELSE pmp END, "
            . "seuil_stock_alerte = " . ((int) $pSpec['seuil_stock_alerte']) . ", "
            . "desiredstock = " . ((int) $pSpec['desiredstock']) . ", "
            . "fk_default_warehouse = " . ((int) $warehouseIds['ALMACEN-OROKUI-01']) . " "
            . "WHERE rowid = " . $pId;
        $db->query($sqlUpdP);
    }
    $productIds[$pKey] = $pId;
}

// Helper to ensure stock exists in a specific warehouse for a product
function ensureProductStock($db, $user, $productId, $warehouseId, $qty, $price, $label, $invCode, $batchLot = '', $sellBy = '') {
    if ($productId <= 0 || $warehouseId <= 0) {
        return;
    }
    $sqlCheck = "SELECT rowid, reel FROM " . MAIN_DB_PREFIX . "product_stock "
              . "WHERE fk_product = " . ((int) $productId)
              . " AND fk_entrepot = " . ((int) $warehouseId) . " LIMIT 1";
    $resCheck = $db->query($sqlCheck);
    if ($resCheck && $db->num_rows($resCheck) > 0) {
        $objS = $db->fetch_object($resCheck);
        if ((float) $objS->reel > 0) {
            return;
        }
    }
    $prod = new Product($db);
    if ($prod->fetch($productId) > 0) {
        if (!empty($batchLot) && (int) $prod->status_batch === 1) {
            $dlc = !empty($sellBy) ? $sellBy : dol_time_plus_duree(dol_now(), 6, 'm');
            $res = $prod->correct_stock_batch(
                $user,
                $warehouseId,
                $qty,
                0, // 0 = add stock
                $label,
                $price,
                $dlc,
                $dlc,
                $batchLot,
                $invCode
            );
        } else {
            $res = $prod->correct_stock(
                $user,
                $warehouseId,
                $qty,
                0, // 0 = add stock
                $label,
                $price,
                $invCode
            );
        }
        if ($res > 0) {
            echo "[OROKUI-SEED] Added stock qty={$qty} for product id={$productId} in warehouse id={$warehouseId}.\n";
        }
    }
}

// Populate initial stock across the 3 warehouses
$whMain   = $warehouseIds['ALMACEN-OROKUI-01'];
$whProd   = $warehouseIds['ALMACEN-PROD-02'];
$whTienda = $warehouseIds['ALMACEN-TIENDA-03'];

// Batch-tracked products
ensureProductStock($db, $user, $productIds['OROKUI-MENGEN-01'], $whMain, 250, 15000, 'Anfangsbestand Rohmaterial Charge A01', 'SEED-INIT-2026', 'LOT-2026-A01');
ensureProductStock($db, $user, $productIds['OROKUI-MENGEN-01'], $whProd, 150, 15000, 'Produktionsbestand Rohmaterial Charge A02', 'SEED-INIT-2026', 'LOT-2026-A02');
ensureProductStock($db, $user, $productIds['OROKUI-RAW-02'], $whMain, 45, 135000, 'Wareneingang Queso Paraguay Charge 2611', 'SEED-INIT-2026', 'LOT-QUESO-2611');
ensureProductStock($db, $user, $productIds['OROKUI-RAW-02'], $whProd, 15, 135000, 'Reifekammer Queso Paraguay Charge 2611', 'SEED-INIT-2026', 'LOT-QUESO-2611');

// Standard stock-tracked products
ensureProductStock($db, $user, $productIds['OROKUI-RAW-01'], $whMain, 80, 85000, 'Wareneingang Almidon de Mandioca (San Pedro)', 'SEED-INIT-2026');
ensureProductStock($db, $user, $productIds['OROKUI-RAW-01'], $whProd, 25, 85000, 'Bereitstellung Produktion Almidon de Mandioca', 'SEED-INIT-2026');
ensureProductStock($db, $user, $productIds['OROKUI-RAW-03'], $whMain, 30, 62000, 'Wareneingang Verpackungsrollen Oro Kui', 'SEED-INIT-2026');
ensureProductStock($db, $user, $productIds['OROKUI-RAW-03'], $whProd, 10, 62000, 'Verpackungslinie Bestand', 'SEED-INIT-2026');

ensureProductStock($db, $user, $productIds['OROKUI-FIN-01'], $whMain, 320, 18000, 'Fertigwareneingang Chipa Tradicional', 'SEED-INIT-2026');
ensureProductStock($db, $user, $productIds['OROKUI-FIN-01'], $whTienda, 120, 18000, 'Filialbestand POS Chipa Tradicional', 'SEED-INIT-2026');
ensureProductStock($db, $user, $productIds['OROKUI-FIN-02'], $whMain, 180, 21000, 'Fertigwareneingang Mbeju Artesanal', 'SEED-INIT-2026');
ensureProductStock($db, $user, $productIds['OROKUI-FIN-02'], $whTienda, 80, 21000, 'Filialbestand POS Mbeju Artesanal', 'SEED-INIT-2026');
ensureProductStock($db, $user, $productIds['OROKUI-FIN-03'], $whMain, 140, 24000, 'Fertigwareneingang Sopa Paraguaya', 'SEED-INIT-2026');
ensureProductStock($db, $user, $productIds['OROKUI-FIN-03'], $whTienda, 50, 24000, 'Filialbestand POS Sopa Paraguaya', 'SEED-INIT-2026');
ensureProductStock($db, $user, $productIds['OROKUI-FIN-04'], $whMain, 210, 14000, 'Fertigwareneingang Cocido Quemado Soluble', 'SEED-INIT-2026');
ensureProductStock($db, $user, $productIds['OROKUI-FIN-04'], $whTienda, 90, 14000, 'Filialbestand POS Cocido Quemado Soluble', 'SEED-INIT-2026');

// ============================================================================
// 5. BOM (Stueckliste) & MRP (Fertigungsauftrag)
// ============================================================================
$bomRef = 'BOM-OROKUI-CHIPA-01';
$bomId = findIdByColumn($db, 'bom_bom', 'ref', $bomRef);
if ($bomId <= 0 && !empty($productIds['OROKUI-FIN-01'])) {
    $bom = new Bom($db);
    $bom->ref = $bomRef;
    $bom->label = "Rezeptur & Stueckliste Chipa Tradicional Oro Ku'i (Losgroesse 100 Packungen)";
    $bom->description = 'Standard-Fertigungsstueckliste fuer 100 Packungen Chipa Tradicional (12 Stk/Packung)';
    $bom->fk_product = $productIds['OROKUI-FIN-01'];
    $bom->bomtype = 0; // Manufacturing
    $bom->qty = 100;
    $bom->efficiency = 1.0;
    $bom->fk_warehouse = $whProd;
    $bom->status = 0;
    $createdBomId = $bom->create($user);
    if ($createdBomId > 0) {
        $bomId = (int) $createdBomId;
        $bom->addLine($productIds['OROKUI-RAW-01'], 2, 0, 0, 1.0, 1);
        $bom->addLine($productIds['OROKUI-RAW-02'], 3, 0, 0, 1.0, 2);
        $bom->addLine($productIds['OROKUI-RAW-03'], 1, 0, 0, 1.0, 3);
        $bom->validate($user);
        // Keep stable human-readable ref for lookups
        $db->query("UPDATE " . MAIN_DB_PREFIX . "bom_bom SET ref = '" . $db->escape($bomRef) . "', status = 1 WHERE rowid = " . $bomId);
        echo "[OROKUI-SEED] Created and validated BOM '{$bomRef}' (id={$bomId}).\n";
    }
}

$moRef = 'MO-OROKUI-2026-001';
$moId = findIdByColumn($db, 'mrp_mo', 'ref', $moRef);
if ($moId <= 0 && $bomId > 0) {
    $mo = new Mo($db);
    $mo->ref = $moRef;
    $mo->label = 'Tagescharge Chipa Tradicional 100 Packungen (Schicht Vormittag)';
    $mo->fk_bom = $bomId;
    $mo->fk_product = $productIds['OROKUI-FIN-01'];
    $mo->qty = 100;
    $mo->fk_warehouse = $whProd;
    $mo->mrptype = 0;
    $mo->date_start_planned = $now - 86400;
    $mo->date_end_planned = $now + 86400 * 2;
    $mo->status = 0;
    $createdMoId = $mo->create($user);
    if ($createdMoId > 0) {
        $moId = (int) $createdMoId;
        $mo->validate($user);
        $db->query("UPDATE " . MAIN_DB_PREFIX . "mrp_mo SET ref = '" . $db->escape($moRef) . "' WHERE rowid = " . $moId);
        echo "[OROKUI-SEED] Created and validated Manufacturing Order '{$moRef}' (id={$moId}).\n";
    }
}

// ============================================================================
// 6. COMMERCIAL PROPOSALS (Angebote)
// ============================================================================
$proposalsSpec = array(
    array(
        'ref_client' => 'PROP-OROKUI-2026-01',
        'tp_key' => 'CU-OROKUI-0002',
        'datep' => $now - 86400 * 14,
        'fin_validite' => $now + 86400 * 16,
        'note_public' => 'Monatsangebot Frische-Sortiment Oro Ku\'i fuer Supermercados Casa Rica (Filialen Asuncion)',
        'close_status' => 2, // Signed / Accepted
        'lines' => array(
            array('prod' => 'OROKUI-FIN-01', 'qty' => 80, 'price' => 35000, 'tva' => 10, 'desc' => 'Chipa Tradicional 12er Packung'),
            array('prod' => 'OROKUI-FIN-02', 'qty' => 50, 'price' => 42000, 'tva' => 10, 'desc' => 'Mbeju Artesanal 6er Packung'),
            array('prod' => 'OROKUI-FIN-03', 'qty' => 30, 'price' => 48000, 'tva' => 10, 'desc' => 'Sopa Paraguaya Casera 1kg Tray'),
            array('prod' => 'OROKUI-SRV-01', 'qty' => 2,  'price' => 75000, 'tva' => 10, 'desc' => 'Kuehlkettenlogistik Asuncion'),
        ),
    ),
    array(
        'ref_client' => 'PROP-OROKUI-2026-02',
        'tp_key' => 'CU-OROKUI-0004',
        'datep' => $now - 86400 * 5,
        'fin_validite' => $now + 86400 * 25,
        'note_public' => 'Angebot Frühstücksbuffet & Kongress-Catering Hotel Guarani Esplendor',
        'close_status' => 0, // Remains Open/Validated
        'lines' => array(
            array('prod' => 'OROKUI-FIN-01', 'qty' => 60, 'price' => 35000, 'tva' => 10, 'desc' => 'Chipa Tradicional Buffet-Packung'),
            array('prod' => 'OROKUI-FIN-02', 'qty' => 40, 'price' => 42000, 'tva' => 10, 'desc' => 'Mbeju Artesanal Hotel-Packung'),
            array('prod' => 'OROKUI-FIN-04', 'qty' => 35, 'price' => 28000, 'tva' => 10, 'desc' => 'Cocido Quemado Soluble 250g'),
        ),
    ),
    array(
        'ref_client' => 'PROP-OROKUI-2026-03',
        'tp_key' => 'CU-OROKUI-0005',
        'datep' => $now - 86400 * 10,
        'fin_validite' => $now + 86400 * 20,
        'note_public' => 'Grosshandels-Rahmenangebot Region Alto Parana (Distribuidora Del Este)',
        'close_status' => 2, // Signed / Accepted
        'lines' => array(
            array('prod' => 'OROKUI-FIN-01', 'qty' => 150, 'price' => 33000, 'tva' => 10, 'desc' => 'Chipa Tradicional Grosshandelstarif'),
            array('prod' => 'OROKUI-FIN-04', 'qty' => 100, 'price' => 26000, 'tva' => 10, 'desc' => 'Cocido Quemado Soluble Grosshandelstarif'),
        ),
    ),
);

foreach ($proposalsSpec as $prSpec) {
    $existingPrId = findIdByColumn($db, 'propal', 'ref_client', $prSpec['ref_client']);
    if ($existingPrId <= 0 && !empty($thirdpartyIds[$prSpec['tp_key']])) {
        $pr = new Propal($db);
        $pr->socid = $thirdpartyIds[$prSpec['tp_key']];
        $pr->ref_client = $prSpec['ref_client'];
        $pr->date = $prSpec['datep'];
        $pr->datep = $prSpec['datep'];
        $pr->fin_validite = $prSpec['fin_validite'];
        $pr->note_public = $prSpec['note_public'];
        $pr->cond_reglement_id = 1;
        $pr->mode_reglement_id = $payIdVir;
        $prId = $pr->create($user);
        if ($prId > 0) {
            foreach ($prSpec['lines'] as $l) {
                $pObj = new Product($db);
                $pObj->fetch($productIds[$l['prod']]);
                $pr->addline(
                    $l['desc'],
                    $l['price'],
                    $l['qty'],
                    $l['tva'],
                    0,
                    0,
                    $productIds[$l['prod']],
                    0,
                    'HT',
                    0,
                    0,
                    (int) $pObj->type
                );
            }
            $pr->valid($user);
            if ($prSpec['close_status'] > 0) {
                $pr->closeProposal($user, $prSpec['close_status'], 'Angenommen durch Kunden (Demo-Belegkette)');
            }
            echo "[OROKUI-SEED] Created proposal '{$pr->ref}' ({$prSpec['ref_client']}, id={$prId}).\n";
        }
    }
}

// ============================================================================
// 7. CUSTOMER SALES ORDERS (Kundenauftraege)
// ============================================================================
$ordersSpec = array(
    array(
        'ref_client' => 'ORD-OROKUI-2026-01',
        'tp_key' => 'CU-OROKUI-0002',
        'date_commande' => $now - 86400 * 12,
        'note_public' => 'Wochenbestellung Supermercados Casa Rica - Filialen Espana & Molas Lopez',
        'billed' => 1,
        'lines' => array(
            array('prod' => 'OROKUI-FIN-01', 'qty' => 80, 'price' => 35000, 'tva' => 10, 'desc' => 'Chipa Tradicional 12er Packung'),
            array('prod' => 'OROKUI-FIN-02', 'qty' => 50, 'price' => 42000, 'tva' => 10, 'desc' => 'Mbeju Artesanal 6er Packung'),
            array('prod' => 'OROKUI-FIN-03', 'qty' => 30, 'price' => 48000, 'tva' => 10, 'desc' => 'Sopa Paraguaya Casera 1kg Tray'),
            array('prod' => 'OROKUI-SRV-01', 'qty' => 2,  'price' => 75000, 'tva' => 10, 'desc' => 'Kuehlkettenlogistik Asuncion'),
        ),
    ),
    array(
        'ref_client' => 'ORD-OROKUI-2026-02',
        'tp_key' => 'CU-OROKUI-0003',
        'date_commande' => $now - 86400 * 7,
        'note_public' => 'Bestellung Cafe & Bistro Karu Pora - Frischelieferung Woche 46',
        'billed' => 1,
        'lines' => array(
            array('prod' => 'OROKUI-FIN-01', 'qty' => 30, 'price' => 35000, 'tva' => 10, 'desc' => 'Chipa Tradicional 12er Packung'),
            array('prod' => 'OROKUI-FIN-02', 'qty' => 25, 'price' => 42000, 'tva' => 10, 'desc' => 'Mbeju Artesanal 6er Packung'),
            array('prod' => 'OROKUI-FIN-04', 'qty' => 20, 'price' => 28000, 'tva' => 10, 'desc' => 'Cocido Quemado Soluble 250g'),
        ),
    ),
    array(
        'ref_client' => 'ORD-OROKUI-2026-03',
        'tp_key' => 'CU-OROKUI-0004',
        'date_commande' => $now - 86400 * 2,
        'note_public' => 'Abrufauftrag Hotel Guarani Esplendor - Konferenzwoche',
        'billed' => 0,
        'lines' => array(
            array('prod' => 'OROKUI-FIN-01', 'qty' => 45, 'price' => 35000, 'tva' => 10, 'desc' => 'Chipa Tradicional Buffet-Packung'),
            array('prod' => 'OROKUI-FIN-03', 'qty' => 25, 'price' => 48000, 'tva' => 10, 'desc' => 'Sopa Paraguaya Casera 1kg Tray'),
            array('prod' => 'OROKUI-SRV-01', 'qty' => 1,  'price' => 75000, 'tva' => 10, 'desc' => 'Express-Zustellung Hotel Guarani'),
        ),
    ),
);

foreach ($ordersSpec as $oSpec) {
    $existingOrdId = findIdByColumn($db, 'commande', 'ref_client', $oSpec['ref_client']);
    if ($existingOrdId <= 0 && !empty($thirdpartyIds[$oSpec['tp_key']])) {
        $ord = new Commande($db);
        $ord->socid = $thirdpartyIds[$oSpec['tp_key']];
        $ord->ref_client = $oSpec['ref_client'];
        $ord->date = $oSpec['date_commande'];
        $ord->date_commande = $oSpec['date_commande'];
        $ord->note_public = $oSpec['note_public'];
        $ord->warehouse_id = $whMain;
        $ord->cond_reglement_id = 1;
        $ord->mode_reglement_id = $payIdVir;
        $ordId = $ord->create($user);
        if ($ordId > 0) {
            foreach ($oSpec['lines'] as $l) {
                $pObj = new Product($db);
                $pObj->fetch($productIds[$l['prod']]);
                $ord->addline(
                    $l['desc'],
                    $l['price'],
                    $l['qty'],
                    $l['tva'],
                    0,
                    0,
                    $productIds[$l['prod']],
                    0,
                    0,
                    0,
                    'HT',
                    0,
                    '',
                    '',
                    (int) $pObj->type
                );
            }
            $ord->valid($user, $whMain);
            if (!empty($oSpec['billed'])) {
                $ord->classifyBilled($user);
            }
            echo "[OROKUI-SEED] Created customer order '{$ord->ref}' ({$oSpec['ref_client']}, id={$ordId}).\n";
        }
    }
}

// ============================================================================
// 8. BANK & CASH ACCOUNTS + INITIAL CAPITAL / FLOAT
// ============================================================================
$cashAccId = findIdByColumn($db, 'bank_account', 'ref', 'CAJA-POS-PYG');
$bankAccId = findIdByColumn($db, 'bank_account', 'ref', 'BANCO-OP-PYG');

function ensureBankEntry($db, $user, $accountId, $date, $oper, $label, $amount, $numChq, $category = '') {
    if ($accountId <= 0) {
        return;
    }
    $sql = "SELECT rowid FROM " . MAIN_DB_PREFIX . "bank "
         . "WHERE fk_account = " . ((int) $accountId)
         . " AND num_chq = '" . $db->escape($numChq) . "' LIMIT 1";
    $res = $db->query($sql);
    if ($res && $db->num_rows($res) > 0) {
        return;
    }
    $acc = new Account($db);
    if ($acc->fetch($accountId) > 0) {
        $lineId = $acc->addline($date, $oper, $label, $amount, $numChq, 0, $user);
        if ($lineId > 0) {
            echo "[OROKUI-SEED] Added bank/cash ledger entry '{$numChq}' ({$amount} PYG) on account id={$accountId}.\n";
        }
    }
}

ensureBankEntry($db, $user, $cashAccId, $now - 86400 * 20, 'LIQ', "Anfangsbestand Kasse / Wechselgeld Oro Ku'i POS", 2500000, 'CAJA-INIT-2026');
ensureBankEntry($db, $user, $bankAccId, $now - 86400 * 20, 'VIR', "Anfangsbestand Operatives Geschaeftskonto Oro Ku'i (PYG)", 25000000, 'BANCO-INIT-2026');
ensureBankEntry($db, $user, $cashAccId, $now - 86400 * 3,  'LIQ', 'Tageslosung Barverkauf Theke Villa Morra (Sammelbuchung)', 485000, 'CAJA-MOSTRADOR-01');
ensureBankEntry($db, $user, $cashAccId, $now - 86400 * 2,  'LIQ', 'Barausgabe Trockeneis & Kuehlakkus Filiale (Kleinbeleg)', -65000, 'CAJA-GASTO-01');

// ============================================================================
// 9. CUSTOMER INVOICES & TAKEPOS RECEIPTS + PAYMENTS
// ============================================================================
$invoicesSpec = array(
    array(
        'ref_client' => 'FAC-OROKUI-2026-01',
        'tp_key' => 'CU-OROKUI-0002',
        'datef' => $now - 86400 * 11,
        'note_public' => 'Rechnung B2B Lieferung Supermercados Casa Rica S.A. (SIFEN-ready)',
        'module_source' => '',
        'pos_source' => '',
        'pay_status' => 'full',
        'pay_mode_id' => $payIdVir,
        'pay_mode_code' => 'VIR',
        'bank_account_id' => $bankAccId,
        'pay_num' => 'VIR-CASARICA-2026-01',
        'lines' => array(
            array('prod' => 'OROKUI-FIN-01', 'qty' => 80, 'price' => 35000, 'tva' => 10, 'desc' => 'Chipa Tradicional 12er Packung'),
            array('prod' => 'OROKUI-FIN-02', 'qty' => 50, 'price' => 42000, 'tva' => 10, 'desc' => 'Mbeju Artesanal 6er Packung'),
            array('prod' => 'OROKUI-FIN-03', 'qty' => 30, 'price' => 48000, 'tva' => 10, 'desc' => 'Sopa Paraguaya Casera 1kg Tray'),
            array('prod' => 'OROKUI-SRV-01', 'qty' => 2,  'price' => 75000, 'tva' => 10, 'desc' => 'Kuehlkettenlogistik Asuncion'),
        ),
    ),
    array(
        'ref_client' => 'FAC-OROKUI-2026-02',
        'tp_key' => 'CU-OROKUI-0003',
        'datef' => $now - 86400 * 6,
        'note_public' => 'Rechnung Gastronomie-Lieferung Cafe & Bistro Karu Pora S.R.L.',
        'module_source' => '',
        'pos_source' => '',
        'pay_status' => 'full',
        'pay_mode_id' => $payIdVir,
        'pay_mode_code' => 'VIR',
        'bank_account_id' => $bankAccId,
        'pay_num' => 'VIR-KARUPORA-2026-01',
        'lines' => array(
            array('prod' => 'OROKUI-FIN-01', 'qty' => 30, 'price' => 35000, 'tva' => 10, 'desc' => 'Chipa Tradicional 12er Packung'),
            array('prod' => 'OROKUI-FIN-02', 'qty' => 25, 'price' => 42000, 'tva' => 10, 'desc' => 'Mbeju Artesanal 6er Packung'),
            array('prod' => 'OROKUI-FIN-04', 'qty' => 20, 'price' => 28000, 'tva' => 10, 'desc' => 'Cocido Quemado Soluble 250g'),
        ),
    ),
    array(
        'ref_client' => 'FAC-OROKUI-2026-03',
        'tp_key' => 'CU-OROKUI-0004',
        'datef' => $now - 86400 * 3,
        'note_public' => 'Rechnung Hotel Guarani Esplendor - Kongress-Catering (50% Anzahlung erhalten)',
        'module_source' => '',
        'pos_source' => '',
        'pay_status' => 'partial',
        'pay_mode_id' => $payIdVir,
        'pay_mode_code' => 'VIR',
        'bank_account_id' => $bankAccId,
        'pay_num' => 'VIR-GUARANI-ANZ-01',
        'lines' => array(
            array('prod' => 'OROKUI-FIN-01', 'qty' => 45, 'price' => 35000, 'tva' => 10, 'desc' => 'Chipa Tradicional Buffet-Packung'),
            array('prod' => 'OROKUI-FIN-03', 'qty' => 25, 'price' => 48000, 'tva' => 10, 'desc' => 'Sopa Paraguaya Casera 1kg Tray'),
            array('prod' => 'OROKUI-SRV-01', 'qty' => 1,  'price' => 75000, 'tva' => 10, 'desc' => 'Express-Zustellung Hotel Guarani'),
        ),
    ),
    array(
        'ref_client' => 'FAC-OROKUI-2026-04',
        'tp_key' => 'CU-OROKUI-0005',
        'datef' => $now - 86400 * 1,
        'note_public' => 'Rechnung Grosshandelslieferung Distribuidora Del Este S.A. (Zahlungsziel 30 Tage)',
        'module_source' => '',
        'pos_source' => '',
        'pay_status' => 'unpaid',
        'pay_mode_id' => $payIdVir,
        'pay_mode_code' => 'VIR',
        'bank_account_id' => $bankAccId,
        'pay_num' => '',
        'lines' => array(
            array('prod' => 'OROKUI-FIN-01', 'qty' => 100, 'price' => 33000, 'tva' => 10, 'desc' => 'Chipa Tradicional Grosshandelspackung'),
            array('prod' => 'OROKUI-FIN-04', 'qty' => 60,  'price' => 26000, 'tva' => 10, 'desc' => 'Cocido Quemado Soluble 250g'),
        ),
    ),
    array(
        'ref_client' => 'POS-OROKUI-2026-01',
        'tp_key' => 'CU-POS-0001',
        'datef' => $now - 86400 * 2,
        'note_public' => "TakePOS Kassenbeleg Terminal 1 - Barverkauf Filiale Oro Ku'i",
        'module_source' => 'takepos',
        'pos_source' => '1',
        'pay_status' => 'full',
        'pay_mode_id' => $payIdLiq,
        'pay_mode_code' => 'LIQ',
        'bank_account_id' => $cashAccId,
        'pay_num' => 'POS-CASH-2026-001',
        'lines' => array(
            array('prod' => 'OROKUI-FIN-01', 'qty' => 4, 'price' => 35000, 'tva' => 10, 'desc' => 'Chipa Tradicional 12er Packung (POS)'),
            array('prod' => 'OROKUI-FIN-02', 'qty' => 2, 'price' => 42000, 'tva' => 10, 'desc' => 'Mbeju Artesanal 6er Packung (POS)'),
            array('prod' => 'OROKUI-FIN-04', 'qty' => 3, 'price' => 28000, 'tva' => 10, 'desc' => 'Cocido Quemado Soluble 250g (POS)'),
        ),
    ),
    array(
        'ref_client' => 'POS-OROKUI-2026-02',
        'tp_key' => 'CU-POS-0001',
        'datef' => $now - 3600 * 6,
        'note_public' => "TakePOS Kassenbeleg Terminal 1 - Barverkauf Nachmittag Oro Ku'i",
        'module_source' => 'takepos',
        'pos_source' => '1',
        'pay_status' => 'full',
        'pay_mode_id' => $payIdLiq,
        'pay_mode_code' => 'LIQ',
        'bank_account_id' => $cashAccId,
        'pay_num' => 'POS-CASH-2026-002',
        'lines' => array(
            array('prod' => 'OROKUI-FIN-01', 'qty' => 3, 'price' => 35000, 'tva' => 10, 'desc' => 'Chipa Tradicional 12er Packung (POS)'),
            array('prod' => 'OROKUI-FIN-03', 'qty' => 2, 'price' => 48000, 'tva' => 10, 'desc' => 'Sopa Paraguaya Casera 1kg Tray (POS)'),
        ),
    ),
);

foreach ($invoicesSpec as $invSpec) {
    $existingInvId = findIdByColumn($db, 'facture', 'ref_client', $invSpec['ref_client']);
    if ($existingInvId <= 0 && !empty($thirdpartyIds[$invSpec['tp_key']])) {
        $fac = new Facture($db);
        $fac->socid = $thirdpartyIds[$invSpec['tp_key']];
        $fac->type = Facture::TYPE_STANDARD;
        $fac->ref_client = $invSpec['ref_client'];
        $fac->date = $invSpec['datef'];
        $fac->date_lim_reglement = $invSpec['datef'] + 86400 * 30;
        $fac->note_public = $invSpec['note_public'];
        $fac->cond_reglement_id = 1;
        $fac->mode_reglement_id = $invSpec['pay_mode_id'];
        $fac->fk_account = $invSpec['bank_account_id'];
        if (!empty($invSpec['module_source'])) {
            $fac->module_source = $invSpec['module_source'];
            $fac->pos_source = $invSpec['pos_source'];
        }
        $facId = $fac->create($user);
        if ($facId > 0) {
            foreach ($invSpec['lines'] as $l) {
                $pObj = new Product($db);
                $pObj->fetch($productIds[$l['prod']]);
                $fac->addline(
                    $l['desc'],
                    $l['price'],
                    $l['qty'],
                    $l['tva'],
                    0,
                    0,
                    $productIds[$l['prod']],
                    0,
                    '',
                    '',
                    0,
                    0,
                    0,
                    'HT',
                    0,
                    (int) $pObj->type
                );
            }
            $fac->validate($user, '', 0);
            $fac->fetch($facId);

            if ($invSpec['pay_status'] === 'full' || $invSpec['pay_status'] === 'partial') {
                $amountToPay = ($invSpec['pay_status'] === 'full')
                    ? (float) $fac->total_ttc
                    : round(((float) $fac->total_ttc) * 0.5, 0);

                $paiement = new Paiement($db);
                $paiement->datepaye = $invSpec['datef'] + 3600;
                $paiement->amounts = array($facId => $amountToPay);
                $paiement->paiementid = $invSpec['pay_mode_id'];
                $paiement->num_payment = $invSpec['pay_num'];
                $paiement->note_private = 'Automatische Zahlungsbuchung (' . $invSpec['ref_client'] . ')';

                $closePaid = ($invSpec['pay_status'] === 'full') ? 1 : 0;
                $paiementId = $paiement->create($user, $closePaid);
                if ($paiementId > 0 && $invSpec['bank_account_id'] > 0) {
                    $paiement->addPaymentToBank(
                        $user,
                        'payment',
                        '(CustomerInvoicePayment)',
                        $invSpec['bank_account_id'],
                        '',
                        ''
                    );
                }
            }
            echo "[OROKUI-SEED] Created invoice '{$fac->ref}' ({$invSpec['ref_client']}, id={$facId}, status={$invSpec['pay_status']}).\n";
        }
    }
}

// ============================================================================
// 10. SUPPLIER ORDERS & SUPPLIER INVOICES (Einkauf & Verbindlichkeiten)
// ============================================================================
$supOrdRef = 'SUPORD-OROKUI-2026-01';
$existingSupOrdId = findIdByColumn($db, 'commande_fournisseur', 'ref_supplier', $supOrdRef);
if ($existingSupOrdId <= 0 && !empty($thirdpartyIds['SU-OROKUI-0001'])) {
    $sOrd = new CommandeFournisseur($db);
    $sOrd->socid = $thirdpartyIds['SU-OROKUI-0001'];
    $sOrd->ref_supplier = $supOrdRef;
    $sOrd->date = $now - 86400 * 15;
    $sOrd->note_public = 'Rohstoffbestellung Maniokstaerke & Agrarrohstoffe (Cooperativa San Pedro)';
    $sOrdId = $sOrd->create($user);
    if ($sOrdId > 0) {
        $sOrd->addline(
            'Almidon de Mandioca Premium (Sack 25 kg)',
            85000,
            60,
            5,
            0,
            0,
            $productIds['OROKUI-RAW-01'],
            0,
            'SP-ALM-25KG',
            0,
            'HT'
        );
        $sOrd->addline(
            'Oro Kui Rohmaterial Charge A (Mengentracking)',
            15000,
            200,
            5,
            0,
            0,
            $productIds['OROKUI-MENGEN-01'],
            0,
            'SP-ROH-A',
            0,
            'HT'
        );
        $sOrd->valid($user);
        echo "[OROKUI-SEED] Created supplier order '{$sOrd->ref}' ({$supOrdRef}, id={$sOrdId}).\n";
    }
}

$supplierInvoicesSpec = array(
    array(
        'ref_supplier' => 'SUPINV-OROKUI-2026-01',
        'tp_key' => 'SU-OROKUI-0001',
        'datef' => $now - 86400 * 13,
        'label' => 'Eingangsrechnung Maniokstaerke & Rohmaterial (Cooperativa San Pedro)',
        'paid' => true,
        'pay_num' => 'VIR-SUP-SANPEDRO-01',
        'lines' => array(
            array('prod' => 'OROKUI-RAW-01',    'qty' => 60,  'pu' => 85000, 'tva' => 5, 'desc' => 'Almidon de Mandioca Premium (Sack 25 kg)'),
            array('prod' => 'OROKUI-MENGEN-01', 'qty' => 200, 'pu' => 15000, 'tva' => 5, 'desc' => 'Oro Kui Rohmaterial Charge A'),
        ),
    ),
    array(
        'ref_supplier' => 'SUPINV-OROKUI-2026-02',
        'tp_key' => 'SU-OROKUI-0002',
        'datef' => $now - 86400 * 4,
        'label' => 'Eingangsrechnung Verpackungsfolien & Etiketten (Envases Paraguay S.A.)',
        'paid' => false,
        'pay_num' => '',
        'lines' => array(
            array('prod' => 'OROKUI-RAW-03', 'qty' => 30, 'pu' => 62000, 'tva' => 10, 'desc' => 'Empaque Termosellado Oro Kui (Rolle 1000 Stk)'),
        ),
    ),
);

foreach ($supplierInvoicesSpec as $sInvSpec) {
    $existingSInvId = findIdByColumn($db, 'facture_fourn', 'ref_supplier', $sInvSpec['ref_supplier']);
    if ($existingSInvId <= 0 && !empty($thirdpartyIds[$sInvSpec['tp_key']])) {
        $sFac = new FactureFournisseur($db);
        $sFac->socid = $thirdpartyIds[$sInvSpec['tp_key']];
        $sFac->ref_supplier = $sInvSpec['ref_supplier'];
        $sFac->label = $sInvSpec['label'];
        $sFac->date = $sInvSpec['datef'];
        $sFac->date_echeance = $sInvSpec['datef'] + 86400 * 30;
        $sFac->note_public = $sInvSpec['label'];
        $sFac->fk_account = $bankAccId;
        $sFacId = $sFac->create($user);
        if ($sFacId > 0) {
            foreach ($sInvSpec['lines'] as $l) {
                $sFac->addline(
                    $l['desc'],
                    $l['pu'],
                    $l['tva'],
                    0,
                    0,
                    $l['qty'],
                    $productIds[$l['prod']],
                    0,
                    0,
                    0,
                    0,
                    0,
                    'HT'
                );
            }
            $sFac->validate($user, '', 0);
            $sFac->fetch($sFacId);

            if (!empty($sInvSpec['paid']) && $bankAccId > 0) {
                $pFourn = new PaiementFourn($db);
                $pFourn->datepaye = $sInvSpec['datef'] + 7200;
                $pFourn->amounts = array($sFacId => (float) $sFac->total_ttc);
                $pFourn->paiementid = $payIdVir;
                $pFourn->num_payment = $sInvSpec['pay_num'];
                $pFournId = $pFourn->create($user, 1);
                if ($pFournId > 0) {
                    $pFourn->addPaymentToBank(
                        $user,
                        'payment_supplier',
                        '(SupplierInvoicePayment)',
                        $bankAccId,
                        '',
                        ''
                    );
                }
            }
            echo "[OROKUI-SEED] Created supplier invoice '{$sFac->ref}' ({$sInvSpec['ref_supplier']}, id={$sFacId}).\n";
        }
    }
}

echo "[OROKUI-SEED] Demo data verification & seeding completed successfully.\n";
