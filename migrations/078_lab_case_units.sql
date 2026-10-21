-- Branch lab cases: number of units (e.g. 3 units of zirconia crown). Existing cases count as 1 unit.
ALTER TABLE lab_cases ADD COLUMN units INTEGER NOT NULL DEFAULT 1
