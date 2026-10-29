-- Merchandise: products sold in the clinic (oral care, orthodontic care, medicines, denture care...), with their own
-- receipts and payments (apart from patient bills), and stock per branch. Products start without prices: the clinic sets them.
CREATE TABLE merch_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT 'Others',
    unit TEXT NOT NULL DEFAULT 'pc',
    price_cents INTEGER,
    cost_cents INTEGER,
    reorder_level INTEGER NOT NULL DEFAULT 0,
    rx_required INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE merch_stock (
    product_id INTEGER NOT NULL REFERENCES merch_products(id),
    branch_id INTEGER NOT NULL REFERENCES branches(id),
    qty INTEGER NOT NULL DEFAULT 0,
    expiry_date TEXT,
    PRIMARY KEY (product_id, branch_id)
);
CREATE TABLE merch_sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    branch_id INTEGER NOT NULL REFERENCES branches(id),
    patient_id INTEGER REFERENCES patients(id),
    buyer_name TEXT NOT NULL DEFAULT '',
    sold_on TEXT NOT NULL,
    subtotal_cents INTEGER NOT NULL DEFAULT 0,
    discount_cents INTEGER NOT NULL DEFAULT 0,
    total_cents INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ok',
    void_reason TEXT NOT NULL DEFAULT '',
    voided_by INTEGER REFERENCES users(id),
    voided_at TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE INDEX idx_merch_sales_branch_day ON merch_sales(branch_id, sold_on);
CREATE TABLE merch_sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES merch_sales(id),
    product_id INTEGER NOT NULL REFERENCES merch_products(id),
    description TEXT NOT NULL,
    qty INTEGER NOT NULL,
    unit_price_cents INTEGER NOT NULL,
    unit_cost_cents INTEGER,
    amount_cents INTEGER NOT NULL
);
CREATE INDEX idx_merch_sale_items_sale ON merch_sale_items(sale_id);
CREATE TABLE merch_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES merch_sales(id),
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
CREATE INDEX idx_merch_payments_sale ON merch_payments(sale_id);
CREATE INDEX idx_merch_payments_day ON merch_payments(branch_id, received_at);
CREATE TABLE merch_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES merch_products(id),
    branch_id INTEGER NOT NULL REFERENCES branches(id),
    kind TEXT NOT NULL,
    qty INTEGER NOT NULL,
    unit_cost_cents INTEGER,
    expiry_date TEXT,
    sale_id INTEGER REFERENCES merch_sales(id),
    notes TEXT NOT NULL DEFAULT '',
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE INDEX idx_merch_moves_product ON merch_moves(product_id, branch_id);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Toothpaste - regular', 'Oral care', 'tube', 0, 1);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Toothpaste - sensitive teeth', 'Oral care', 'tube', 0, 2);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Toothpaste - kids', 'Oral care', 'tube', 0, 3);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Toothpaste - whitening', 'Oral care', 'tube', 0, 4);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Toothbrush - soft', 'Oral care', 'pc', 0, 5);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Toothbrush - kids', 'Oral care', 'pc', 0, 6);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Electric toothbrush replacement heads', 'Oral care', 'pack', 0, 7);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Mouthwash - regular', 'Oral care', 'bottle', 0, 8);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Mouthwash - fluoride', 'Oral care', 'bottle', 0, 9);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Mouthwash - chlorhexidine', 'Oral care', 'bottle', 0, 10);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Dental floss', 'Oral care', 'pc', 0, 11);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Floss threaders', 'Oral care', 'pack', 0, 12);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Interdental brushes', 'Oral care', 'pack', 0, 13);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Tongue cleaner', 'Oral care', 'pc', 0, 14);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Orthodontic toothbrush (V-cut)', 'Orthodontic care', 'pc', 0, 15);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Orthodontic wax', 'Orthodontic care', 'pack', 0, 16);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Orthodontic elastics', 'Orthodontic care', 'pack', 0, 17);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Retainer case', 'Orthodontic care', 'pc', 0, 18);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Retainer / aligner cleaning tablets', 'Orthodontic care', 'box', 0, 19);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Aligner chewies', 'Orthodontic care', 'pack', 0, 20);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Orthodontic care kit', 'Orthodontic care', 'kit', 0, 21);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Mefenamic acid 500 mg capsule', 'Medicines', 'capsule', 0, 22);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Paracetamol 500 mg tablet', 'Medicines', 'tablet', 0, 23);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Ibuprofen 400 mg tablet', 'Medicines', 'tablet', 0, 24);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Amoxicillin 500 mg capsule', 'Medicines', 'capsule', 1, 25);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Co-amoxiclav 625 mg tablet', 'Medicines', 'tablet', 1, 26);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Clindamycin 300 mg capsule', 'Medicines', 'capsule', 1, 27);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Metronidazole 500 mg tablet', 'Medicines', 'tablet', 1, 28);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Denture adhesive', 'Denture care', 'tube', 0, 29);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Denture cleansing tablets', 'Denture care', 'box', 0, 30);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Denture brush', 'Denture care', 'pc', 0, 31);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Denture box', 'Denture care', 'pc', 0, 32);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Take-home whitening kit', 'Whitening & others', 'kit', 0, 33);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Whitening pen', 'Whitening & others', 'pc', 0, 34);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Night guard case', 'Whitening & others', 'pc', 0, 35);
INSERT INTO merch_products (name, category, unit, rx_required, sort_order) VALUES ('Fluoride gel', 'Whitening & others', 'tube', 0, 36)
