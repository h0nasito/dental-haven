-- Announcements for staff, and the monthly duty schedule (who is on duty at each branch each day).
CREATE TABLE announcements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  branch_id INTEGER REFERENCES branches(id),
  title TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  pinned INTEGER NOT NULL DEFAULT 0,
  starts_on TEXT NOT NULL,
  ends_on TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_announcements_dates ON announcements(starts_on, ends_on);
CREATE TABLE duty_assignments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  work_date TEXT NOT NULL,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  note TEXT NOT NULL DEFAULT '',
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  UNIQUE (branch_id, work_date, employee_id)
);
CREATE INDEX idx_duty_date ON duty_assignments(work_date, branch_id);
