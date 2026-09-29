-- Dentist commission, manual options.
-- 1) Per bill line: auto (the dentist's usual rate), a manual %, or a fixed amount (e.g. 0 on an ortho package line).
ALTER TABLE invoice_items ADD COLUMN commission_mode TEXT NOT NULL DEFAULT 'auto';
ALTER TABLE invoice_items ADD COLUMN commission_bp INTEGER;
ALTER TABLE invoice_items ADD COLUMN commission_cents INTEGER;
-- 2) Manual entries, e.g. at each ortho adjustment when the patient pays part of the package.
-- Counted in the payroll cutoff that contains earned_on. amount = base x rate when a rate is given, or typed directly.
CREATE TABLE dentist_commissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  earned_on TEXT NOT NULL,
  invoice_id INTEGER REFERENCES invoices(id),
  payment_id INTEGER REFERENCES payments(id),
  description TEXT NOT NULL DEFAULT '',
  base_cents INTEGER,
  rate_bp INTEGER,
  amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
  status TEXT NOT NULL DEFAULT 'valid' CHECK (status IN ('valid','void')),
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  voided_by INTEGER REFERENCES users(id),
  voided_at TEXT
);
CREATE INDEX idx_dentist_commissions ON dentist_commissions(employee_id, earned_on)
