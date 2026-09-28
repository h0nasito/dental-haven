-- Dentist pay: daily rate + commission. Commission is counted on each procedure line once it's done:
-- (line amount - its share of the invoice discount - lab fee) x the dentist's commission %.
ALTER TABLE invoice_items ADD COLUMN dentist_id INTEGER REFERENCES users(id);
ALTER TABLE invoice_items ADD COLUMN done_on TEXT;
ALTER TABLE invoice_items ADD COLUMN lab_fee_cents INTEGER NOT NULL DEFAULT 0;
ALTER TABLE invoice_items ADD COLUMN lab_case_id INTEGER REFERENCES lab_cases(id);
CREATE INDEX idx_invoice_items_dentist ON invoice_items(dentist_id, done_on);

-- Existing lines: the dentist of the invoice's appointment, done on the appointment date (or the issue date).
UPDATE invoice_items SET
  dentist_id = (SELECT a.dentist_id FROM invoices i JOIN appointments a ON a.id = i.appointment_id WHERE i.id = invoice_items.invoice_id),
  done_on = (SELECT COALESCE(substr(a.start_at, 1, 10), i.issued_at, substr(i.created_at, 1, 10))
             FROM invoices i LEFT JOIN appointments a ON a.id = i.appointment_id WHERE i.id = invoice_items.invoice_id);

CREATE TABLE dentist_pay_rates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  daily_rate_cents INTEGER NOT NULL DEFAULT 0,
  commission_bp INTEGER NOT NULL DEFAULT 0,          -- 4000 = 40%
  effective_from TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE TABLE dentist_service_rates (
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  service_id INTEGER NOT NULL REFERENCES services(id),
  commission_bp INTEGER NOT NULL,
  PRIMARY KEY (employee_id, service_id)
);

ALTER TABLE payroll_lines ADD COLUMN kind TEXT NOT NULL DEFAULT 'staff';
ALTER TABLE payroll_lines ADD COLUMN daily_pay_cents INTEGER;
ALTER TABLE payroll_lines ADD COLUMN commission_cents INTEGER;
ALTER TABLE payroll_lines ADD COLUMN commission_base_cents INTEGER;
ALTER TABLE payroll_lines ADD COLUMN commission_items INTEGER NOT NULL DEFAULT 0;
