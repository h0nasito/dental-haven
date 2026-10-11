-- Payroll: additions (allowances, quota hit, incentives, bonuses) and deductions (cash advance, loans, ...) per employee per period,
-- and regular allowances per employee (per day present or fixed per cutoff) that are added automatically.
CREATE TABLE employee_allowances (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  name TEXT NOT NULL,
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  basis TEXT NOT NULL DEFAULT 'per_day' CHECK (basis IN ('per_day','per_cutoff')),
  active INTEGER NOT NULL DEFAULT 1,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_employee_allowances ON employee_allowances(employee_id);
CREATE TABLE payroll_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  period_id INTEGER NOT NULL REFERENCES payroll_periods(id),
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  kind TEXT NOT NULL CHECK (kind IN ('addition','deduction')),
  name TEXT NOT NULL,
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  note TEXT NOT NULL DEFAULT '',
  allowance_id INTEGER REFERENCES employee_allowances(id),
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_payroll_items ON payroll_items(period_id, employee_id);
