-- Fixed salary: a monthly-salary employee paid half the salary every cutoff whatever the time clock shows (e.g. works from home).
ALTER TABLE employees ADD COLUMN fixed_pay INTEGER NOT NULL DEFAULT 0
