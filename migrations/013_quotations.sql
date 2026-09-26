-- Price quotations (estimates) a dentist or staff member prepares for a patient or prospective patient.
CREATE TABLE quotations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  number TEXT UNIQUE,
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  patient_id INTEGER REFERENCES patients(id),
  client_name TEXT NOT NULL DEFAULT '',
  client_contact TEXT NOT NULL DEFAULT '',
  dentist_id INTEGER REFERENCES users(id),
  appointment_id INTEGER REFERENCES appointments(id),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','issued','accepted','declined')),
  valid_until TEXT,
  subtotal_cents INTEGER NOT NULL DEFAULT 0,
  discount_cents INTEGER NOT NULL DEFAULT 0,
  total_cents INTEGER NOT NULL DEFAULT 0,
  notes TEXT NOT NULL DEFAULT '',
  invoice_id INTEGER REFERENCES invoices(id),
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT,
  issued_at TEXT
);
CREATE INDEX idx_quotations_branch ON quotations(branch_id, created_at);
CREATE INDEX idx_quotations_patient ON quotations(patient_id);

CREATE TABLE quotation_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  quotation_id INTEGER NOT NULL REFERENCES quotations(id),
  price_item_id INTEGER REFERENCES price_items(id),
  service_id INTEGER REFERENCES services(id),
  description TEXT NOT NULL,
  tooth TEXT NOT NULL DEFAULT '',
  qty INTEGER NOT NULL DEFAULT 1,
  unit_price_cents INTEGER NOT NULL DEFAULT 0,
  discount_cents INTEGER NOT NULL DEFAULT 0,
  amount_cents INTEGER NOT NULL DEFAULT 0,
  sample_price INTEGER NOT NULL DEFAULT 0,
  seq INTEGER NOT NULL DEFAULT 0
);
