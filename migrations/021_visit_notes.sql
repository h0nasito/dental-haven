-- "New progress note" form: one visit = services done (per tooth), notes, attachments, recall, optional bill, patient signature.
-- Drafts keep the form as typed (lines_json) and create nothing else until saved.
CREATE TABLE visit_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  branch_id INTEGER REFERENCES branches(id),
  dentist_id INTEGER REFERENCES users(id),
  visit_date TEXT NOT NULL,
  recall_date TEXT,
  recall_reason TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT '',
  lines_json TEXT NOT NULL DEFAULT '[]',
  bill_discount_bp INTEGER NOT NULL DEFAULT 0,
  create_bill INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','saved')),
  invoice_id INTEGER REFERENCES invoices(id),
  note_id INTEGER REFERENCES clinical_notes(id),
  followup_id INTEGER REFERENCES follow_ups(id),
  signature_name TEXT NOT NULL DEFAULT '',
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT
);
CREATE INDEX idx_visit_notes_patient ON visit_notes(patient_id, status);
ALTER TABLE procedures ADD COLUMN visit_note_id INTEGER REFERENCES visit_notes(id);
ALTER TABLE patient_documents ADD COLUMN visit_note_id INTEGER REFERENCES visit_notes(id)
