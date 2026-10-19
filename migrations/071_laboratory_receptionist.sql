-- The position "Lab Receptionist" is now called "Laboratory Receptionist" (with its own access role, lab_receptionist).
UPDATE employees SET position = 'Laboratory Receptionist' WHERE position = 'Lab Receptionist';
UPDATE evaluation_forms SET target_positions = REPLACE(target_positions, 'Lab Receptionist', 'Laboratory Receptionist') WHERE target_positions LIKE '%Lab Receptionist%';
