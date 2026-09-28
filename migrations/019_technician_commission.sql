-- Dental technicians: daily rate + commission. Commission is added by hand on a lab work (outside clinic) or a
-- branch lab case, and counts in the payroll cutoff when that work leaves the laboratory (delivered).
CREATE TABLE lab_commissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  work_id INTEGER REFERENCES lab_works(id),
  case_id INTEGER REFERENCES lab_cases(id),
  amount_cents INTEGER NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_lab_commissions_emp ON lab_commissions(employee_id);
