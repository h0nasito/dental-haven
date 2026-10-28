-- Morning email to approvers listing requests still waiting for them (leave, reimbursements, field work,
-- overtime, payroll). Each user can turn it off in Profile settings. Only who/when/status is kept, not the email text.
ALTER TABLE users ADD COLUMN notify_approvals INTEGER NOT NULL DEFAULT 1;
CREATE TABLE approval_emails (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  sent_day TEXT NOT NULL,
  items INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX idx_approval_emails_day ON approval_emails(sent_day, user_id)
