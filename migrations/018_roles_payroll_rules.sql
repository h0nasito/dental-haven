-- Access roles within Staff (Receptionist, HR, Supervisor, Cashier, General). users.role keeps the base role
-- (super_admin / dentist / staff / receptionist); users.access_role picks the permission set.
ALTER TABLE users ADD COLUMN access_role TEXT;

-- Overtime counts only when a supervisor approves it.
-- ot_minutes: minutes after branch closing (detected)
ALTER TABLE time_records ADD COLUMN ot_minutes INTEGER NOT NULL DEFAULT 0;
ALTER TABLE time_records ADD COLUMN ot_approved_minutes INTEGER NOT NULL DEFAULT 0;
ALTER TABLE time_records ADD COLUMN ot_approved_by INTEGER REFERENCES users(id);
ALTER TABLE time_records ADD COLUMN ot_approved_at TEXT;
ALTER TABLE time_records ADD COLUMN ot_note TEXT NOT NULL DEFAULT '';
ALTER TABLE time_records ADD COLUMN late_minutes INTEGER NOT NULL DEFAULT 0;

CREATE TABLE holidays (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('regular', 'special')),
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);

CREATE TABLE late_warnings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  month TEXT NOT NULL,              -- YYYY-MM
  late_count INTEGER NOT NULL,
  email_status TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE (employee_id, month)
);

ALTER TABLE payroll_lines ADD COLUMN basic_pay_cents INTEGER;
ALTER TABLE payroll_lines ADD COLUMN ot_minutes INTEGER NOT NULL DEFAULT 0;
ALTER TABLE payroll_lines ADD COLUMN ot_pay_cents INTEGER;
ALTER TABLE payroll_lines ADD COLUMN holiday_pay_cents INTEGER;
ALTER TABLE payroll_lines ADD COLUMN late_deduction_cents INTEGER;
