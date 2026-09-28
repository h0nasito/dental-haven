-- Consumables inventory: one item catalog, stock per location (branch or in-house lab), and a history of every change.
CREATE TABLE inventory_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  unit TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL,
  unit_price_cents INTEGER,
  supplier TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_inventory_items_category ON inventory_items(category);

CREATE TABLE inventory_locations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  branch_id INTEGER REFERENCES branches(id),
  laboratory_id INTEGER REFERENCES laboratories(id),
  active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE inventory_stock (
  location_id INTEGER NOT NULL REFERENCES inventory_locations(id),
  item_id INTEGER NOT NULL REFERENCES inventory_items(id),
  qty REAL NOT NULL DEFAULT 0,
  reorder_level REAL,
  expiry_date TEXT,
  last_counted_at TEXT,
  updated_by INTEGER REFERENCES users(id),
  updated_at TEXT NOT NULL,
  PRIMARY KEY (location_id, item_id)
);

CREATE TABLE inventory_moves (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  location_id INTEGER NOT NULL REFERENCES inventory_locations(id),
  item_id INTEGER NOT NULL REFERENCES inventory_items(id),
  kind TEXT NOT NULL,            -- count | received | used | expired | damaged | transfer_out | adjust
  qty_change REAL NOT NULL,
  qty_after REAL NOT NULL,
  expiry_date TEXT,
  note TEXT NOT NULL DEFAULT '',
  user_id INTEGER REFERENCES users(id),
  at TEXT NOT NULL
);
CREATE INDEX idx_inventory_moves_item ON inventory_moves(location_id, item_id, id);
