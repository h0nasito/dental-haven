-- Laboratory expenses (materials, rent, utilities, courier, ...), recorded by lab billing staff.
-- They count as soon as they are saved; a mistake is voided with a reason, never deleted.
CREATE TABLE lab_expenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lab_id INTEGER NOT NULL REFERENCES laboratories(id),
  expense_date TEXT NOT NULL,
  category TEXT NOT NULL,
  item TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  qty REAL NOT NULL DEFAULT 1,
  unit_price_cents INTEGER,
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  payee TEXT NOT NULL DEFAULT '',
  method TEXT NOT NULL DEFAULT 'cash',
  account TEXT NOT NULL DEFAULT '',
  reference TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  receipt_stored TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','void')),
  void_reason TEXT NOT NULL DEFAULT '',
  voided_by INTEGER REFERENCES users(id),
  voided_at TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_lab_expenses_lab_date ON lab_expenses(lab_id, expense_date)
