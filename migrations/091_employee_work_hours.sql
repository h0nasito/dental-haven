-- An employee's own working hours for attendance (lates and overtime), e.g. an associate on 10:00-18:00.
-- Empty = the usual rule (staff: clinic staff hours; dentists: their dentist schedule or the branch opening hours).
ALTER TABLE employees ADD COLUMN work_start TEXT;
ALTER TABLE employees ADD COLUMN work_end TEXT
