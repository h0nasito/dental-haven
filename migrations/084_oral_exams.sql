-- Soft tissue and occlusion findings for the dental chart. One row per exam (dated), so the history is kept.
CREATE TABLE oral_exams (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  exam_date TEXT NOT NULL,
  gingivitis TEXT NOT NULL DEFAULT '',
  gingivitis_extent TEXT NOT NULL DEFAULT '',
  periodontitis TEXT NOT NULL DEFAULT '',
  periodontitis_extent TEXT NOT NULL DEFAULT '',
  frenum TEXT NOT NULL DEFAULT '',
  tongue TEXT NOT NULL DEFAULT '',
  buccal_mucosa TEXT NOT NULL DEFAULT '',
  palate TEXT NOT NULL DEFAULT '',
  molar_right TEXT NOT NULL DEFAULT '',
  molar_left TEXT NOT NULL DEFAULT '',
  canine_right TEXT NOT NULL DEFAULT '',
  canine_left TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  recorded_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_oral_exams_patient ON oral_exams(patient_id, exam_date);
