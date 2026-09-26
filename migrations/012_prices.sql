-- Price list for the website chat (and later the site). Shown publicly only after the clinic confirms it.
CREATE TABLE price_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  service_id INTEGER REFERENCES services(id),
  price_from_cents INTEGER,
  price_to_cents INTEGER,
  unit TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  keywords TEXT NOT NULL DEFAULT '',
  sort_order INTEGER NOT NULL DEFAULT 0,
  published INTEGER NOT NULL DEFAULT 1,
  sample INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  updated_by INTEGER REFERENCES users(id)
);
