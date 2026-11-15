-- Kept for records only: excusing a DTR exception no longer forgives lateness (late is late; a wrong time is corrected).
ALTER TABLE time_records ADD COLUMN late_forgiven INTEGER NOT NULL DEFAULT 0
