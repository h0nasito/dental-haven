-- A saved visit (progress note) can be cancelled: it leaves the progress notes list and its open recall is cancelled.
-- The record (including the patient's signature) is kept for the clinic's records.
ALTER TABLE visit_notes ADD COLUMN cancelled_at TEXT;
ALTER TABLE visit_notes ADD COLUMN cancelled_by INTEGER REFERENCES users(id);
ALTER TABLE visit_notes ADD COLUMN cancel_reason TEXT NOT NULL DEFAULT ''
