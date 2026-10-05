-- Automatic daily collection report: a log of each send.
CREATE TABLE report_sends (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_day TEXT NOT NULL,
  recipients TEXT NOT NULL DEFAULT '',
  sent INTEGER NOT NULL DEFAULT 0,
  error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
)
