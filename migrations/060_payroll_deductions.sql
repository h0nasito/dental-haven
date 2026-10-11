-- Regular payroll deductions per employee (SSS, PhilHealth, Pag-IBIG, tax, loans): fixed amounts typed by HR,
-- deducted automatically on the chosen cutoffs; loans stop when the loan total is paid.
CREATE TABLE employee_deductions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  name TEXT NOT NULL,
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  schedule TEXT NOT NULL DEFAULT 'every' CHECK (schedule IN ('every','first','second','split')),
  loan_total_cents INTEGER,
  reference TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_employee_deductions ON employee_deductions(employee_id);
ALTER TABLE payroll_items ADD COLUMN deduction_id INTEGER REFERENCES employee_deductions(id);
