-- Email dentists about their appointments (approved, rescheduled, cancelled).
ALTER TABLE users ADD COLUMN notify_email INTEGER NOT NULL DEFAULT 1;

-- One row per email. The email text itself is NOT stored (it contains the patient's name);
-- it is built from the appointment at sending time.
CREATE TABLE dentist_emails (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  appointment_id INTEGER NOT NULL REFERENCES appointments(id),
  user_id INTEGER NOT NULL REFERENCES users(id),
  event TEXT NOT NULL,              -- confirmed | rescheduled | cancelled | reassigned
  previous TEXT NOT NULL DEFAULT '',-- for reschedules: the old day/time/branch (no patient data)
  status TEXT NOT NULL DEFAULT 'pending', -- pending | sent | failed | not_set_up | demo | skipped
  error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  sent_at TEXT
);
CREATE INDEX idx_dentist_emails_appt ON dentist_emails(appointment_id);
