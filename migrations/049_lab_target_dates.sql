-- Lab cases: target dates for the patient's trial fitting and final installation. A case can go direct to
-- installation (no trial fitting).
ALTER TABLE lab_cases ADD COLUMN try_in_on TEXT;
ALTER TABLE lab_cases ADD COLUMN install_on TEXT;
ALTER TABLE lab_cases ADD COLUMN no_try_in INTEGER NOT NULL DEFAULT 0
