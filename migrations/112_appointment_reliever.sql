-- A dentist may cover as a reliever outside their schedule (or at another branch): staff confirm it, and it is remembered.
ALTER TABLE appointments ADD COLUMN off_schedule_ok INTEGER NOT NULL DEFAULT 0
