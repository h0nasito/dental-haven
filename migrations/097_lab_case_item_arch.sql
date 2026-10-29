-- Branch lab case items: upper, lower or both arches (like outside clinic works).
ALTER TABLE lab_case_items ADD COLUMN arch TEXT NOT NULL DEFAULT ''
