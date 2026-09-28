-- Patient profile: staff remarks (front-desk notes, not clinical) and dentist diagnoses.
CREATE TABLE patient_remarks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  body TEXT NOT NULL,
  author_id INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_patient_remarks ON patient_remarks(patient_id);
CREATE TABLE patient_diagnoses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  diagnosed_on TEXT NOT NULL,
  tooth TEXT NOT NULL DEFAULT '',
  diagnosis TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','resolved')),
  dentist_id INTEGER REFERENCES users(id),
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT
);
CREATE INDEX idx_patient_diagnoses ON patient_diagnoses(patient_id);
ALTER TABLE invoice_items ADD COLUMN tooth TEXT NOT NULL DEFAULT '';
CREATE TABLE payment_signatures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  stored_name TEXT NOT NULL DEFAULT '',
  not_signed_reason TEXT NOT NULL DEFAULT '',
  captured_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
ALTER TABLE payments ADD COLUMN signature_id INTEGER REFERENCES payment_signatures(id)
