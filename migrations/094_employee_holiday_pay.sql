-- Per employee: holiday pay (regular holiday worked = double pay, special non-working day worked = +30%,
-- unworked regular holiday = 1 day when that setting is on). Off for commission-based staff. On for everyone at first,
-- so payroll doesn't change until someone is unticked.
ALTER TABLE employees ADD COLUMN holiday_pay INTEGER NOT NULL DEFAULT 1
