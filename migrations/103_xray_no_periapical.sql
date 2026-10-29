-- Periapical X-rays are procedures (progress notes and the patient's bill), not the X-ray section.
DELETE FROM xray_types WHERE name = 'Periapical' AND id NOT IN (SELECT type_id FROM xray_items WHERE type_id IS NOT NULL);
UPDATE xray_types SET active = 0 WHERE name = 'Periapical'
