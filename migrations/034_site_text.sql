-- Website texts edited per section (Administration → Website sections). Only texts changed from the default are stored.
CREATE TABLE site_text (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL DEFAULT '',
  updated_at TEXT,
  updated_by INTEGER REFERENCES users(id)
);
