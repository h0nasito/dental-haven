-- Trial fitting of a lab case (try-in): the result, the agreement text, and the signatures of the patient and the dentist.
CREATE TABLE lab_case_fittings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL REFERENCES lab_cases(id),
  fitted_on TEXT NOT NULL,
  result TEXT NOT NULL CHECK (result IN ('approved','adjust','remake')),
  notes TEXT NOT NULL DEFAULT '',
  agreement_text TEXT NOT NULL DEFAULT '',
  signer_name TEXT NOT NULL DEFAULT '',
  signer_relation TEXT NOT NULL DEFAULT 'patient',
  patient_signature TEXT,
  not_signed_reason TEXT NOT NULL DEFAULT '',
  dentist_id INTEGER REFERENCES users(id),
  dentist_signature TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_lab_case_fittings_case ON lab_case_fittings(case_id);
