-- An employee's workplace can be the laboratory (DSDL) instead of a clinic branch, and the lab has its own payroll periods.
ALTER TABLE employees ADD COLUMN lab_id INTEGER REFERENCES laboratories(id);
ALTER TABLE payroll_periods ADD COLUMN lab_id INTEGER REFERENCES laboratories(id)
