-- A clinical note added later to an existing progress-note row (date + dentist), e.g. the dentist's additional notes.
ALTER TABLE clinical_notes ADD COLUMN visit_date TEXT;
ALTER TABLE clinical_notes ADD COLUMN visit_dentist TEXT
