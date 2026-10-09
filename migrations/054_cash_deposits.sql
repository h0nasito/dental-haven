-- Cash deposits: the cashier records each bank deposit of the branch's cash collections, with the deposit slip.
CREATE TABLE cash_deposits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  deposit_date TEXT NOT NULL,
  cash_from TEXT NOT NULL DEFAULT '',
  cash_to TEXT NOT NULL DEFAULT '',
  bank TEXT NOT NULL DEFAULT '',
  account TEXT NOT NULL DEFAULT '',
  slip_no TEXT NOT NULL DEFAULT '',
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  expected_cents INTEGER NOT NULL DEFAULT 0,
  deposited_by TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  slip_stored TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','void')),
  void_reason TEXT NOT NULL DEFAULT '',
  voided_by INTEGER REFERENCES users(id),
  voided_at TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_cash_deposits_branch ON cash_deposits(branch_id, deposit_date);
