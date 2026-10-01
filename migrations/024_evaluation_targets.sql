-- Each evaluation form is for one kind of staff (e.g. Dental Assistant, Receptionist); the dentist picks one person.
ALTER TABLE evaluation_forms ADD COLUMN target_positions TEXT NOT NULL DEFAULT ''
