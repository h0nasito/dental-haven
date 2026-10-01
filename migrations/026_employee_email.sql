-- Work email for an employee (used to create their login account).
ALTER TABLE employees ADD COLUMN email TEXT NOT NULL DEFAULT ''
