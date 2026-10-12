-- Service incentive leave (leave with pay): 5 days a year for regular employees by default; HR can set a different number per employee.
ALTER TABLE leave_requests ADD COLUMN with_pay INTEGER NOT NULL DEFAULT 0;
ALTER TABLE employees ADD COLUMN paid_leave_days REAL;
