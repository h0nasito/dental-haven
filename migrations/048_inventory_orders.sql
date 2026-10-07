-- Monthly order lists per inventory location (branch or lab): made by staff before month end, approved, ordered, received.
CREATE TABLE inventory_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  location_id INTEGER NOT NULL REFERENCES inventory_locations(id),
  for_month TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','submitted','approved','ordered','received','cancelled')),
  notes TEXT NOT NULL DEFAULT '',
  review_note TEXT NOT NULL DEFAULT '',
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  submitted_by INTEGER REFERENCES users(id),
  submitted_at TEXT,
  approved_by INTEGER REFERENCES users(id),
  approved_at TEXT,
  ordered_at TEXT,
  received_by INTEGER REFERENCES users(id),
  received_at TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_inventory_orders ON inventory_orders(location_id, for_month);
CREATE TABLE inventory_order_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL REFERENCES inventory_orders(id) ON DELETE CASCADE,
  item_id INTEGER REFERENCES inventory_items(id),
  name TEXT NOT NULL,
  unit TEXT NOT NULL DEFAULT '',
  qty REAL NOT NULL CHECK (qty > 0),
  approved_qty REAL,
  received_qty REAL,
  unit_price_cents INTEGER,
  note TEXT NOT NULL DEFAULT '',
  sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_inventory_order_lines ON inventory_order_lines(order_id)
