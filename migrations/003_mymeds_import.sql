-- Import from MyMedsPH: link records to their MyMedsPH IDs so re-importing updates instead of duplicating.
ALTER TABLE patients ADD COLUMN middle_name TEXT NOT NULL DEFAULT '';
ALTER TABLE patients ADD COLUMN civil_status TEXT NOT NULL DEFAULT '';
ALTER TABLE patients ADD COLUMN occupation TEXT NOT NULL DEFAULT '';
ALTER TABLE patients ADD COLUMN emergency_contact TEXT NOT NULL DEFAULT '';
ALTER TABLE patients ADD COLUMN emergency_phone TEXT NOT NULL DEFAULT '';
ALTER TABLE patients ADD COLUMN legacy_id TEXT;
CREATE UNIQUE INDEX idx_patients_legacy ON patients(legacy_id);
ALTER TABLE procedures ADD COLUMN legacy_key TEXT;
CREATE UNIQUE INDEX idx_procedures_legacy ON procedures(legacy_key);
ALTER TABLE clinical_notes ADD COLUMN legacy_key TEXT;
CREATE UNIQUE INDEX idx_notes_legacy ON clinical_notes(legacy_key);
ALTER TABLE treatment_plan_items ADD COLUMN legacy_key TEXT;
CREATE UNIQUE INDEX idx_plan_items_legacy ON treatment_plan_items(legacy_key);
ALTER TABLE follow_ups ADD COLUMN legacy_key TEXT;
CREATE UNIQUE INDEX idx_followups_legacy ON follow_ups(legacy_key);

-- Bills from MyMedsPH are kept as history on the patient record. They are not counted in the new sales reports.
CREATE TABLE legacy_bills (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  bill_date TEXT NOT NULL,
  service TEXT NOT NULL DEFAULT '',
  item TEXT NOT NULL DEFAULT '',
  qty INTEGER NOT NULL DEFAULT 1,
  unit_price_cents INTEGER NOT NULL DEFAULT 0,
  discount_cents INTEGER NOT NULL DEFAULT 0,
  total_cents INTEGER NOT NULL DEFAULT 0,
  status_code TEXT NOT NULL DEFAULT '',
  remarks TEXT NOT NULL DEFAULT '',
  legacy_key TEXT NOT NULL UNIQUE
);
CREATE INDEX idx_legacy_bills_patient ON legacy_bills(patient_id, bill_date);

CREATE TABLE import_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  filename TEXT NOT NULL DEFAULT '',
  branch_id INTEGER REFERENCES branches(id),
  status TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '{}',
  started_by INTEGER REFERENCES users(id),
  started_at TEXT NOT NULL,
  finished_at TEXT
)
