-- Bank deposits: one or more pictures of the deposit slip per deposit (the bank-validated slip, the cash count, ...).
CREATE TABLE cash_deposit_photos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  deposit_id INTEGER NOT NULL REFERENCES cash_deposits(id),
  stored_name TEXT NOT NULL,
  uploaded_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_cash_deposit_photos ON cash_deposit_photos(deposit_id);
INSERT INTO cash_deposit_photos (deposit_id, stored_name, uploaded_by, created_at)
  SELECT id, slip_stored, created_by, created_at FROM cash_deposits WHERE slip_stored != '';
