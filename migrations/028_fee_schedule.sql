-- The clinic's billing price list (fee schedule), by category. Used when adding progress notes and bill lines.
CREATE TABLE fee_schedule (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  unit TEXT NOT NULL DEFAULT '',
  price_cents INTEGER NOT NULL DEFAULT 0,
  category TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT,
  updated_by INTEGER REFERENCES users(id)
);
CREATE INDEX idx_fee_schedule_cat ON fee_schedule(category, active)
