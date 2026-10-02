-- Time clock "on the field": the punch is marked as field work with a reason, and the day counts for payroll only after
-- a supervisor / HR / admin approves it.
ALTER TABLE time_punches ADD COLUMN field INTEGER NOT NULL DEFAULT 0;
ALTER TABLE time_punches ADD COLUMN field_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE time_records ADD COLUMN field_status TEXT CHECK (field_status IN ('pending','approved','declined'));
ALTER TABLE time_records ADD COLUMN field_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE time_records ADD COLUMN field_reviewed_by INTEGER REFERENCES users(id);
ALTER TABLE time_records ADD COLUMN field_reviewed_at TEXT;
ALTER TABLE time_records ADD COLUMN field_review_note TEXT NOT NULL DEFAULT '';
