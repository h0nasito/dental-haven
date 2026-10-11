-- Monthly bills per branch (rent, electricity, internet, ...): recorded each month as an expense in one click.
CREATE TABLE branch_bills (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  category TEXT NOT NULL,
  item TEXT NOT NULL,
  payee TEXT NOT NULL DEFAULT '',
  amount_cents INTEGER NOT NULL DEFAULT 0,
  due_day INTEGER,
  method TEXT NOT NULL DEFAULT 'cash',
  active INTEGER NOT NULL DEFAULT 1,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_branch_bills_branch ON branch_bills(branch_id);
ALTER TABLE expenses ADD COLUMN bill_id INTEGER REFERENCES branch_bills(id);
ALTER TABLE expenses ADD COLUMN bill_month TEXT NOT NULL DEFAULT '';
