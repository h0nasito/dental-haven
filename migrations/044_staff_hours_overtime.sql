-- Staff working hours (8:00 to 5:00) for lates and overtime, overtime eligibility per employee, and the short lunch.
ALTER TABLE employees ADD COLUMN ot_eligible INTEGER NOT NULL DEFAULT 1;
ALTER TABLE time_records ADD COLUMN short_lunch INTEGER NOT NULL DEFAULT 0;
UPDATE employees SET ot_eligible = 0 WHERE user_id IN (SELECT id FROM users WHERE role = 'dentist');
UPDATE employees SET ot_eligible = 0 WHERE (SELECT c.basis FROM compensation c WHERE c.employee_id = employees.id ORDER BY c.effective_from DESC, c.id DESC LIMIT 1) IN ('percentage', 'per_case', 'daily_commission')
