-- Patient profile photo (kept privately in UPLOAD_DIR/patient_photos, shown only to staff who can see the patient).
ALTER TABLE patients ADD COLUMN photo TEXT;
