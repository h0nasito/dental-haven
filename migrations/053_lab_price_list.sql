-- Each laboratory's price list, used to fill invoice lines and work prices.
CREATE TABLE lab_price_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lab_id INTEGER NOT NULL REFERENCES laboratories(id),
  category TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL,
  price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
  unit TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_lab_price_items ON lab_price_items(lab_id, active, sort_order);
ALTER TABLE laboratories ADD COLUMN email TEXT NOT NULL DEFAULT ''
