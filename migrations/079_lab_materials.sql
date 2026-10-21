-- The laboratory's materials (Zirconia, E.max, PFM...): picked for each case item, editable by the lab.
CREATE TABLE lab_materials (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
)
