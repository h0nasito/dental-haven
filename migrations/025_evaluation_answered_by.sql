-- Who answers each evaluation form: dentists, the Head Dentist, or management (admin).
ALTER TABLE evaluation_forms ADD COLUMN answered_by TEXT NOT NULL DEFAULT 'dentists'
