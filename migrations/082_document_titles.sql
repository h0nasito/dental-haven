-- A name staff can give an uploaded file (e.g. "Panoramic x-ray before extraction") so the doctor can find it; empty = show the original file name.
ALTER TABLE patient_documents ADD COLUMN title TEXT NOT NULL DEFAULT '';
