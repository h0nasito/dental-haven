-- Who deleted (archived) a patient, when and why, for the "Deleted patients" list and restoring.
ALTER TABLE patients ADD COLUMN deleted_at TEXT;
ALTER TABLE patients ADD COLUMN deleted_by INTEGER REFERENCES users(id);
ALTER TABLE patients ADD COLUMN deleted_reason TEXT NOT NULL DEFAULT '';
