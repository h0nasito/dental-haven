-- Progress notes waiting for a bill: the cashier creates the bill from the note, or marks it as not needing one.
ALTER TABLE visit_notes ADD COLUMN bill_skipped_at TEXT;
ALTER TABLE visit_notes ADD COLUMN bill_skipped_by INTEGER REFERENCES users(id)
