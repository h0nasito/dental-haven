-- Daily expense details: time, item name, quantity x unit price, who spent/bought it, supplier, notes and a receipt photo.
ALTER TABLE expenses ADD COLUMN expense_time TEXT NOT NULL DEFAULT '';
ALTER TABLE expenses ADD COLUMN item TEXT NOT NULL DEFAULT '';
ALTER TABLE expenses ADD COLUMN qty REAL NOT NULL DEFAULT 1;
ALTER TABLE expenses ADD COLUMN unit_price_cents INTEGER;
ALTER TABLE expenses ADD COLUMN spent_by TEXT NOT NULL DEFAULT '';
ALTER TABLE expenses ADD COLUMN notes TEXT NOT NULL DEFAULT '';
ALTER TABLE expenses ADD COLUMN receipt_stored TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_expenses_branch_date ON expenses(branch_id, expense_date)
