-- Leave forms: employees file a leave; HR or anyone allowed to approve leave approves or disapproves it.
CREATE TABLE leave_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  branch_id INTEGER REFERENCES branches(id),
  leave_type TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  half_day TEXT NOT NULL DEFAULT '' CHECK (half_day IN ('', 'am', 'pm')),
  days REAL NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  attachment TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','disapproved','cancelled')),
  review_note TEXT NOT NULL DEFAULT '',
  reviewed_by INTEGER REFERENCES users(id),
  reviewed_at TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_leave_requests_emp ON leave_requests(employee_id, start_date);
CREATE INDEX idx_leave_requests_status ON leave_requests(status);
