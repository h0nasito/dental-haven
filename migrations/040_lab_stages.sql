-- migrate: foreign_keys off
-- Laboratory work stages: Accepted, Setting, Designing, Fabricating, Trimming, Polishing, Quality control,
-- Out for trial fitting, On hold, Ready / packed, Delivered (plus Remake and Cancelled).
CREATE TABLE lab_cases_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lab_id INTEGER NOT NULL REFERENCES laboratories(id),
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  dentist_id INTEGER REFERENCES users(id),
  case_type TEXT NOT NULL,
  teeth TEXT NOT NULL DEFAULT '',
  shade TEXT NOT NULL DEFAULT '',
  material TEXT NOT NULL DEFAULT '',
  instructions TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent','accepted','setting','designing','fabricating','trimming','polishing','quality_control','try_in','on_hold','ready','delivered','remake','cancelled')),
  sent_on TEXT NOT NULL,
  due_on TEXT,
  completed_on TEXT,
  lab_fee_cents INTEGER,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT
);
INSERT INTO lab_cases_new (id, lab_id, branch_id, patient_id, dentist_id, case_type, teeth, shade, material, instructions, status,
  sent_on, due_on, completed_on, lab_fee_cents, created_by, created_at, updated_at)
SELECT id, lab_id, branch_id, patient_id, dentist_id, case_type, teeth, shade, material, instructions,
  CASE status WHEN 'received' THEN 'accepted' WHEN 'in_progress' THEN 'fabricating' ELSE status END,
  sent_on, due_on, completed_on, lab_fee_cents, created_by, created_at, updated_at
FROM lab_cases;
DROP TABLE lab_cases;
ALTER TABLE lab_cases_new RENAME TO lab_cases;
CREATE INDEX idx_lab_cases_status ON lab_cases(lab_id, status);
UPDATE lab_case_events SET status = 'accepted' WHERE status = 'received';
UPDATE lab_case_events SET status = 'fabricating' WHERE status = 'in_progress';
UPDATE lab_work_events SET status = 'accepted' WHERE status = 'received';
UPDATE lab_work_events SET status = 'fabricating' WHERE status = 'in_progress';
CREATE TABLE lab_works_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  number TEXT NOT NULL UNIQUE,
  lab_id INTEGER NOT NULL REFERENCES laboratories(id),
  client_id INTEGER NOT NULL REFERENCES lab_clients(id),
  clinic_name TEXT NOT NULL,
  doctor TEXT NOT NULL DEFAULT '',
  contact_number TEXT NOT NULL DEFAULT '',
  patient_ref TEXT NOT NULL DEFAULT '',
  case_type TEXT NOT NULL,
  units INTEGER NOT NULL DEFAULT 1,
  arch TEXT NOT NULL DEFAULT '' CHECK (arch IN ('', 'upper', 'lower', 'both')),
  teeth TEXT NOT NULL DEFAULT '',
  shade TEXT NOT NULL DEFAULT '',
  material TEXT NOT NULL DEFAULT '',
  instructions TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'accepted' CHECK (status IN ('accepted','setting','designing','fabricating','trimming','polishing','quality_control','try_in','on_hold','ready','delivered','remake','cancelled')),
  received_on TEXT NOT NULL,
  due_on TEXT,
  delivered_on TEXT,
  price_cents INTEGER,
  invoice_id INTEGER REFERENCES lab_invoices(id),
  due_soon_notified INTEGER NOT NULL DEFAULT 0,
  overdue_notified INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
INSERT INTO lab_works_new (id, number, lab_id, client_id, clinic_name, doctor, contact_number, patient_ref, case_type, units, arch, teeth,
  shade, material, instructions, status, received_on, due_on, delivered_on, price_cents, invoice_id, due_soon_notified, overdue_notified,
  created_by, created_at, updated_at)
SELECT id, number, lab_id, client_id, clinic_name, doctor, contact_number, patient_ref, case_type, units, arch, teeth,
  shade, material, instructions, CASE status WHEN 'received' THEN 'accepted' WHEN 'in_progress' THEN 'fabricating' ELSE status END,
  received_on, due_on, delivered_on, price_cents, invoice_id, due_soon_notified, overdue_notified, created_by, created_at, updated_at
FROM lab_works;
DROP TABLE lab_works;
ALTER TABLE lab_works_new RENAME TO lab_works;
CREATE INDEX idx_lab_works_status ON lab_works(lab_id, status, due_on);
CREATE INDEX idx_lab_works_client ON lab_works(client_id)
