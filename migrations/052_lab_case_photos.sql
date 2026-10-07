-- Reference photos for a lab case (shade, intraoral, models), kept privately like other patient files.
CREATE TABLE lab_case_photos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL REFERENCES lab_cases(id),
  stored_name TEXT NOT NULL,
  caption TEXT NOT NULL DEFAULT '',
  uploaded_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_lab_case_photos ON lab_case_photos(case_id)
