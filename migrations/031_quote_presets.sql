-- The clinic's own list of quotation items (name, usual price, unit, type, section, note), editable by staff who make quotations.
CREATE TABLE quote_presets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  unit_price_cents INTEGER NOT NULL DEFAULT 0,
  unit_label TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'item',
  section TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT,
  updated_by INTEGER REFERENCES users(id)
)
