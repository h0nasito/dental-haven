-- The dental technician working on an outside-clinic lab work (an employee; optional).
ALTER TABLE lab_works ADD COLUMN technician_id INTEGER REFERENCES employees(id)
