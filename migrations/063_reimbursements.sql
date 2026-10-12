-- Reimbursements: an employee asks back money they spent for the clinic; HR approves; approved ones are added to the
-- salary in the payroll cutoff that covers the approval date (or the next draft payroll after it).
CREATE TABLE reimbursements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  branch_id INTEGER REFERENCES branches(id),
  spent_on TEXT NOT NULL,
  category TEXT NOT NULL,
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  details TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  receipt TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','disapproved','cancelled')),
  review_note TEXT NOT NULL DEFAULT '',
  reviewed_by INTEGER REFERENCES users(id),
  reviewed_at TEXT,
  period_id INTEGER REFERENCES payroll_periods(id),
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_reimbursements_emp ON reimbursements(employee_id, status);
ALTER TABLE payroll_items ADD COLUMN reimbursement_id INTEGER REFERENCES reimbursements(id);
