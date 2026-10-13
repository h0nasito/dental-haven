-- Quotation options: reference photos per option (e.g. how zirconia vs. porcelain crowns look) for the patient.
CREATE TABLE quotation_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  quotation_id INTEGER NOT NULL REFERENCES quotations(id),
  plan TEXT NOT NULL DEFAULT '',
  stored_name TEXT NOT NULL,
  caption TEXT NOT NULL DEFAULT '',
  seq INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_quotation_images ON quotation_images(quotation_id);
