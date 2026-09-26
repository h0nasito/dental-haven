-- MyMedsPH-style permissions and new modules: prescriptions, certificates, expenses,
-- account credit, dental chart and laboratory cases.

-- Existing installations: give roles the new, finer-grained permissions that match what they could already do.
INSERT INTO role_permissions (role, permission) SELECT role, 'patients.contact' FROM role_permissions WHERE permission = 'patients.view';
INSERT INTO role_permissions (role, permission) SELECT role, 'bookings.view' FROM role_permissions WHERE permission = 'bookings.manage';
INSERT INTO role_permissions (role, permission) SELECT role, 'calendar.birthdays' FROM role_permissions WHERE permission = 'appointments.view';
INSERT INTO role_permissions (role, permission) SELECT role, 'calendar.events' FROM role_permissions WHERE permission = 'appointments.view';
INSERT INTO role_permissions (role, permission) SELECT role, 'bills.edit' FROM role_permissions WHERE permission = 'billing.manage';
INSERT INTO role_permissions (role, permission) SELECT role, 'payments.add' FROM role_permissions WHERE permission = 'billing.manage';
INSERT INTO role_permissions (role, permission) SELECT role, 'progress.add' FROM role_permissions WHERE permission = 'clinical.edit';
INSERT INTO role_permissions (role, permission) SELECT role, 'progress.actions' FROM role_permissions WHERE permission = 'clinical.edit';
INSERT INTO role_permissions (role, permission) SELECT role, 'plans.add' FROM role_permissions WHERE permission = 'clinical.edit';
INSERT INTO role_permissions (role, permission) SELECT role, 'plans.edit' FROM role_permissions WHERE permission = 'clinical.edit';
INSERT INTO role_permissions (role, permission) SELECT role, 'plans.generate' FROM role_permissions WHERE permission = 'clinical.edit';
INSERT INTO role_permissions (role, permission) SELECT role, 'chart.edit' FROM role_permissions WHERE permission = 'clinical.edit';
INSERT INTO role_permissions (role, permission) SELECT role, 'rx.create' FROM role_permissions WHERE permission = 'clinical.edit';
INSERT INTO role_permissions (role, permission) SELECT role, 'rx.edit' FROM role_permissions WHERE permission = 'clinical.edit';
INSERT INTO role_permissions (role, permission) SELECT role, 'cert.create' FROM role_permissions WHERE permission = 'clinical.edit';
INSERT INTO role_permissions (role, permission) SELECT role, 'cert.edit' FROM role_permissions WHERE permission = 'clinical.edit';

-- Dentist details printed on prescriptions and certificates
ALTER TABLE users ADD COLUMN license_no TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN ptr_no TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN s2_no TEXT NOT NULL DEFAULT '';

CREATE TABLE prescriptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  branch_id INTEGER REFERENCES branches(id),
  prescriber_id INTEGER REFERENCES users(id),
  prescribed_on TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  deleted INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT
);
CREATE TABLE prescription_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prescription_id INTEGER NOT NULL REFERENCES prescriptions(id),
  medicine TEXT NOT NULL,
  dosage TEXT NOT NULL DEFAULT '',
  quantity TEXT NOT NULL DEFAULT '',
  instructions TEXT NOT NULL DEFAULT '',
  seq INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE certificates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  branch_id INTEGER REFERENCES branches(id),
  issued_by INTEGER REFERENCES users(id),
  kind TEXT NOT NULL DEFAULT 'dental',
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  issued_on TEXT NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT
);

CREATE TABLE expenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  expense_date TEXT NOT NULL,
  category TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  payee TEXT NOT NULL DEFAULT '',
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  method TEXT NOT NULL DEFAULT 'cash',
  reference TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','posted','void')),
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  posted_by INTEGER REFERENCES users(id),
  posted_at TEXT,
  void_reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_expenses_branch_date ON expenses(branch_id, expense_date);

-- Account credit ledger. 'deposit' = money received in advance (counts as a collection);
-- 'applied' = credit used on a bill (not a new collection); 'refund' = credit given back.
CREATE TABLE patient_credits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  kind TEXT NOT NULL CHECK (kind IN ('deposit','applied','refund')),
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  method TEXT NOT NULL DEFAULT '',
  reference TEXT NOT NULL DEFAULT '',
  invoice_id INTEGER REFERENCES invoices(id),
  payment_id INTEGER REFERENCES payments(id),
  entry_date TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'valid' CHECK (status IN ('valid','void')),
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_credits_patient ON patient_credits(patient_id);

-- Dental chart: one row per recorded finding/treatment on a tooth (FDI numbering).
CREATE TABLE chart_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  tooth TEXT NOT NULL,
  surfaces TEXT NOT NULL DEFAULT '',
  condition TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  recorded_by INTEGER REFERENCES users(id),
  recorded_on TEXT NOT NULL,
  deleted INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_chart_patient ON chart_entries(patient_id, tooth);

-- Laboratories (e.g. DSDL) and the cases sent to them.
CREATE TABLE laboratories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  address TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE user_labs (
  user_id INTEGER NOT NULL REFERENCES users(id),
  lab_id INTEGER NOT NULL REFERENCES laboratories(id),
  PRIMARY KEY (user_id, lab_id)
);
CREATE TABLE lab_cases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lab_id INTEGER NOT NULL REFERENCES laboratories(id),
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  dentist_id INTEGER REFERENCES users(id),
  case_type TEXT NOT NULL,
  teeth TEXT NOT NULL DEFAULT '',
  shade TEXT NOT NULL DEFAULT '',
  material TEXT NOT NULL DEFAULT '',
  instructions TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent','received','in_progress','ready','delivered','remake','cancelled')),
  sent_on TEXT NOT NULL,
  due_on TEXT,
  completed_on TEXT,
  lab_fee_cents INTEGER,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT
);
CREATE INDEX idx_lab_cases_status ON lab_cases(lab_id, status);
CREATE TABLE lab_case_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL REFERENCES lab_cases(id),
  user_id INTEGER REFERENCES users(id),
  status TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
)
;
ALTER TABLE prescriptions ADD COLUMN legacy_key TEXT;
CREATE UNIQUE INDEX idx_rx_legacy ON prescriptions(legacy_key);
ALTER TABLE certificates ADD COLUMN legacy_key TEXT;
CREATE UNIQUE INDEX idx_cert_legacy ON certificates(legacy_key)
