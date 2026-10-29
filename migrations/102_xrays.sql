-- X-ray section: X-rays have their own records, receipts and payments, apart from progress notes and patient bills.
-- Walk-ins (not clinic patients) are allowed; outside dentists who refer patients earn a rebate, paid out (usually in December).
CREATE TABLE xray_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    price_cents INTEGER,
    sort_order INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1
);
INSERT INTO xray_types (name, sort_order) VALUES ('Periapical', 1);
INSERT INTO xray_types (name, sort_order) VALUES ('Panoramic', 2);
INSERT INTO xray_types (name, sort_order) VALUES ('Cephalometric - lateral', 3);
INSERT INTO xray_types (name, sort_order) VALUES ('Cephalometric - PA view', 4);
INSERT INTO xray_types (name, sort_order) VALUES ('TMJ', 5);
INSERT INTO xray_types (name, sort_order) VALUES ('CBCT', 6);
CREATE TABLE xray_referrers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    clinic TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    rebate_bp INTEGER,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE xray_rebate_payouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER NOT NULL REFERENCES xray_referrers(id),
    paid_on TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    method TEXT NOT NULL DEFAULT 'cash',
    account TEXT NOT NULL DEFAULT '',
    reference TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ok',
    void_reason TEXT NOT NULL DEFAULT '',
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE TABLE xrays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    branch_id INTEGER NOT NULL REFERENCES branches(id),
    patient_id INTEGER REFERENCES patients(id),
    walkin_name TEXT NOT NULL DEFAULT '',
    walkin_phone TEXT NOT NULL DEFAULT '',
    taken_on TEXT NOT NULL,
    requested_by INTEGER REFERENCES users(id),
    referrer_id INTEGER REFERENCES xray_referrers(id),
    taken_by INTEGER REFERENCES users(id),
    notes TEXT NOT NULL DEFAULT '',
    subtotal_cents INTEGER NOT NULL DEFAULT 0,
    discount_cents INTEGER NOT NULL DEFAULT 0,
    total_cents INTEGER NOT NULL DEFAULT 0,
    rebate_cents INTEGER NOT NULL DEFAULT 0,
    rebate_payout_id INTEGER REFERENCES xray_rebate_payouts(id),
    status TEXT NOT NULL DEFAULT 'ok',
    void_reason TEXT NOT NULL DEFAULT '',
    voided_by INTEGER REFERENCES users(id),
    voided_at TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT
);
CREATE INDEX idx_xrays_branch_day ON xrays(branch_id, taken_on);
CREATE INDEX idx_xrays_patient ON xrays(patient_id);
CREATE INDEX idx_xrays_referrer ON xrays(referrer_id);
CREATE TABLE xray_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    xray_id INTEGER NOT NULL REFERENCES xrays(id),
    type_id INTEGER REFERENCES xray_types(id),
    description TEXT NOT NULL,
    tooth TEXT NOT NULL DEFAULT '',
    price_cents INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_xray_items_xray ON xray_items(xray_id);
CREATE TABLE xray_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    xray_id INTEGER NOT NULL REFERENCES xrays(id),
    branch_id INTEGER NOT NULL REFERENCES branches(id),
    amount_cents INTEGER NOT NULL,
    method TEXT NOT NULL,
    account TEXT NOT NULL DEFAULT '',
    reference TEXT NOT NULL DEFAULT '',
    received_at TEXT NOT NULL,
    received_by INTEGER REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'valid',
    void_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX idx_xray_payments_xray ON xray_payments(xray_id);
CREATE INDEX idx_xray_payments_day ON xray_payments(branch_id, received_at);
CREATE TABLE xray_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    xray_id INTEGER NOT NULL REFERENCES xrays(id),
    stored_name TEXT NOT NULL,
    mime TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    original_name TEXT NOT NULL DEFAULT '',
    uploaded_by INTEGER REFERENCES users(id),
    uploaded_at TEXT NOT NULL
);
CREATE INDEX idx_xray_files_xray ON xray_files(xray_id)
