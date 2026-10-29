-- X-rays added in a progress note: the procedure stays in the dentist's record; the charge is an X-ray record (X-ray section).
ALTER TABLE procedures ADD COLUMN xray_id INTEGER REFERENCES xrays(id);
ALTER TABLE xrays ADD COLUMN visit_note_id INTEGER REFERENCES visit_notes(id)
