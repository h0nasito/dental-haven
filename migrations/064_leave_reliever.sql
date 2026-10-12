-- Leave forms: who covers the work while the employee is on leave (NULL with reliever_na = 1 means "N/A, no one available").
ALTER TABLE leave_requests ADD COLUMN reliever_id INTEGER REFERENCES employees(id);
ALTER TABLE leave_requests ADD COLUMN reliever_na INTEGER NOT NULL DEFAULT 0;
