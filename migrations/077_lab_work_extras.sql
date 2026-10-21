-- Additional charges on an outside work (e.g. 3D printed cast, rush fee): billed together with the work.
CREATE TABLE lab_work_extras (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  work_id INTEGER NOT NULL REFERENCES lab_works(id),
  description TEXT NOT NULL,
  qty INTEGER NOT NULL DEFAULT 1,
  unit_price_cents INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_lab_work_extras ON lab_work_extras(work_id)
