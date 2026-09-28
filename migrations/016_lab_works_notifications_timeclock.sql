-- Outside-clinic lab works (other clinics sending work to our lab), their invoices and payments,
-- in-app notifications, and the selfie + location time clock.

CREATE TABLE lab_clients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lab_id INTEGER NOT NULL REFERENCES laboratories(id),
  clinic_name TEXT NOT NULL,
  doctor TEXT NOT NULL DEFAULT '',
  contact_number TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '',
  address TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_lab_clients_lab ON lab_clients(lab_id, clinic_name);

CREATE TABLE lab_works (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  number TEXT NOT NULL UNIQUE,
  lab_id INTEGER NOT NULL REFERENCES laboratories(id),
  client_id INTEGER NOT NULL REFERENCES lab_clients(id),
  clinic_name TEXT NOT NULL,
  doctor TEXT NOT NULL DEFAULT '',
  contact_number TEXT NOT NULL DEFAULT '',
  patient_ref TEXT NOT NULL DEFAULT '',
  case_type TEXT NOT NULL,
  units INTEGER NOT NULL DEFAULT 1,
  arch TEXT NOT NULL DEFAULT '' CHECK (arch IN ('', 'upper', 'lower', 'both')),
  teeth TEXT NOT NULL DEFAULT '',
  shade TEXT NOT NULL DEFAULT '',
  material TEXT NOT NULL DEFAULT '',
  instructions TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'received' CHECK (status IN ('received','in_progress','ready','delivered','remake','cancelled')),
  received_on TEXT NOT NULL,
  due_on TEXT,
  delivered_on TEXT,
  price_cents INTEGER,
  invoice_id INTEGER REFERENCES lab_invoices(id),
  due_soon_notified INTEGER NOT NULL DEFAULT 0,
  overdue_notified INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_lab_works_status ON lab_works(lab_id, status, due_on);
CREATE INDEX idx_lab_works_client ON lab_works(client_id);

CREATE TABLE lab_work_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  work_id INTEGER NOT NULL REFERENCES lab_works(id),
  user_id INTEGER REFERENCES users(id),
  status TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE lab_invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  number TEXT UNIQUE,
  lab_id INTEGER NOT NULL REFERENCES laboratories(id),
  client_id INTEGER NOT NULL REFERENCES lab_clients(id),
  clinic_name TEXT NOT NULL,
  doctor TEXT NOT NULL DEFAULT '',
  contact_number TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','issued','void')),
  issued_on TEXT,
  due_on TEXT,
  subtotal_cents INTEGER NOT NULL DEFAULT 0,
  discount_cents INTEGER NOT NULL DEFAULT 0,
  discount_note TEXT NOT NULL DEFAULT '',
  total_cents INTEGER NOT NULL DEFAULT 0,
  paid_cents INTEGER NOT NULL DEFAULT 0,
  notes TEXT NOT NULL DEFAULT '',
  void_reason TEXT NOT NULL DEFAULT '',
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_lab_invoices_client ON lab_invoices(client_id);

CREATE TABLE lab_invoice_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL REFERENCES lab_invoices(id),
  work_id INTEGER REFERENCES lab_works(id),
  description TEXT NOT NULL,
  qty INTEGER NOT NULL DEFAULT 1,
  unit_price_cents INTEGER NOT NULL DEFAULT 0,
  discount_cents INTEGER NOT NULL DEFAULT 0,
  amount_cents INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE lab_payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL REFERENCES lab_invoices(id),
  receipt_no TEXT NOT NULL UNIQUE,
  amount_cents INTEGER NOT NULL,
  method TEXT NOT NULL,
  reference TEXT NOT NULL DEFAULT '',
  received_on TEXT NOT NULL,
  received_by INTEGER REFERENCES users(id),
  status TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','void')),
  void_reason TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  link TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  read_at TEXT
);
CREATE INDEX idx_notifications_user ON notifications(user_id, read_at, id);

-- Time clock
ALTER TABLE branches ADD COLUMN latitude REAL;
ALTER TABLE branches ADD COLUMN longitude REAL;
ALTER TABLE branches ADD COLUMN clock_radius_m INTEGER NOT NULL DEFAULT 150;

CREATE TABLE time_punches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  time_record_id INTEGER REFERENCES time_records(id),
  kind TEXT NOT NULL CHECK (kind IN ('in','out')),
  at TEXT NOT NULL,
  latitude REAL,
  longitude REAL,
  accuracy_m REAL,
  distance_m REAL,
  location_ok INTEGER,          -- 1 inside the branch radius, 0 outside, NULL when not checked
  photo TEXT,                   -- stored file name in UPLOAD_DIR/timeclock (deleted after the retention period)
  created_at TEXT NOT NULL
);
CREATE INDEX idx_time_punches_emp ON time_punches(employee_id, at);
