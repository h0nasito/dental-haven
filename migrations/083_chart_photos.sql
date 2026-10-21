-- Photos attached when recording on the dental chart (kept in the patient's Uploads, linked to the chart entry).
ALTER TABLE patient_documents ADD COLUMN chart_entry_id INTEGER REFERENCES chart_entries(id);
