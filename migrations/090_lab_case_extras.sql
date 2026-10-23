-- Additional charges on a branch lab case (rush fee, model cast, different pontic…), billed with the case.
CREATE TABLE lab_case_extras (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL REFERENCES lab_cases(id),
  description TEXT NOT NULL,
  qty INTEGER NOT NULL DEFAULT 1,
  unit_price_cents INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_lab_case_extras ON lab_case_extras(case_id)
