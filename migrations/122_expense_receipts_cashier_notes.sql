-- Expenses: several receipt photos per expense (e.g. a grocery run). Bills: a note for the cashier, also typed on the progress note.
CREATE TABLE expense_receipts (
  id INTEGER PRIMARY KEY,
  expense_id INTEGER NOT NULL REFERENCES expenses(id),
  stored_name TEXT NOT NULL,
  uploaded_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_expense_receipts_expense ON expense_receipts(expense_id);
INSERT INTO expense_receipts (expense_id, stored_name, uploaded_by, created_at)
  SELECT id, receipt_stored, created_by, created_at FROM expenses WHERE receipt_stored != '';
ALTER TABLE invoices ADD COLUMN cashier_note TEXT NOT NULL DEFAULT '';
ALTER TABLE visit_notes ADD COLUMN cashier_note TEXT NOT NULL DEFAULT ''
