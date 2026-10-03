-- Same as 040_lab_stages.sql for PostgreSQL: change the status list in place.
ALTER TABLE lab_cases DROP CONSTRAINT IF EXISTS lab_cases_status_check;
UPDATE lab_cases SET status = 'accepted' WHERE status = 'received';
UPDATE lab_cases SET status = 'fabricating' WHERE status = 'in_progress';
ALTER TABLE lab_cases ADD CONSTRAINT lab_cases_status_check CHECK (status IN ('sent','accepted','setting','designing','fabricating','trimming','polishing','quality_control','try_in','on_hold','ready','delivered','remake','cancelled'));
UPDATE lab_case_events SET status = 'accepted' WHERE status = 'received';
UPDATE lab_case_events SET status = 'fabricating' WHERE status = 'in_progress';
UPDATE lab_work_events SET status = 'accepted' WHERE status = 'received';
UPDATE lab_work_events SET status = 'fabricating' WHERE status = 'in_progress';
ALTER TABLE lab_works DROP CONSTRAINT IF EXISTS lab_works_status_check;
UPDATE lab_works SET status = 'accepted' WHERE status = 'received';
UPDATE lab_works SET status = 'fabricating' WHERE status = 'in_progress';
ALTER TABLE lab_works ALTER COLUMN status SET DEFAULT 'accepted';
ALTER TABLE lab_works ADD CONSTRAINT lab_works_status_check CHECK (status IN ('accepted','setting','designing','fabricating','trimming','polishing','quality_control','try_in','on_hold','ready','delivered','remake','cancelled'))
