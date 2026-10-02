-- Time clock at laboratories: each lab can have its own location, and its attendance is handled by one branch.
ALTER TABLE laboratories ADD COLUMN latitude REAL;
ALTER TABLE laboratories ADD COLUMN longitude REAL;
ALTER TABLE laboratories ADD COLUMN clock_radius_m INTEGER NOT NULL DEFAULT 150;
ALTER TABLE laboratories ADD COLUMN branch_id INTEGER REFERENCES branches(id);
ALTER TABLE time_punches ADD COLUMN lab_id INTEGER REFERENCES laboratories(id);
