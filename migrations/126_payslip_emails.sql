-- "Your payslip is ready" emails per approved payroll period (no amounts in the email: the link needs a sign-in).
CREATE TABLE payslip_emails (
  id INTEGER PRIMARY KEY,
  period_id INTEGER NOT NULL REFERENCES payroll_periods(id),
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  email TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  error TEXT NOT NULL DEFAULT '',
  sent_at TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_payslip_emails_period ON payslip_emails(period_id, employee_id)
