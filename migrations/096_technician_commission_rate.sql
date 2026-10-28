-- Technician commission: a % per technician of what the clinic pays for the works and cases assigned to them,
-- counted in the payroll cutoff when the payment is received. Branch cases get a technician too.
ALTER TABLE employees ADD COLUMN lab_commission_bp INTEGER;
ALTER TABLE lab_cases ADD COLUMN technician_id INTEGER REFERENCES employees(id)
