-- Dental Haven core schema.
-- Written in portable SQL: SQLite for development/demo, PostgreSQL for production.
-- app/migrate.py rewrites "INTEGER PRIMARY KEY AUTOINCREMENT" to "BIGSERIAL PRIMARY KEY" for Postgres.
-- Dates/times are stored as ISO text in clinic local time (Asia/Manila): 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM'.
-- Money is stored as integer centavos.

CREATE TABLE branches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  address TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '',
  map_url TEXT NOT NULL DEFAULT '',
  hours_text TEXT NOT NULL DEFAULT '',
  intro TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('super_admin','dentist','staff','receptionist')),
  active INTEGER NOT NULL DEFAULT 1,
  must_change_password INTEGER NOT NULL DEFAULT 1,
  failed_logins INTEGER NOT NULL DEFAULT 0,
  locked_until TEXT,
  last_login_at TEXT,
  created_at TEXT NOT NULL,
  created_by INTEGER REFERENCES users(id)
);

CREATE TABLE user_branches (
  user_id INTEGER NOT NULL REFERENCES users(id),
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  PRIMARY KEY (user_id, branch_id)
);

-- Role-level access. super_admin always has everything and is not stored here.
CREATE TABLE role_permissions (
  role TEXT NOT NULL,
  permission TEXT NOT NULL,
  PRIMARY KEY (role, permission)
);

CREATE TABLE sessions (
  id_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  active_branch_id INTEGER REFERENCES branches(id)
);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL,
  actor_id INTEGER REFERENCES users(id),
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id INTEGER,
  branch_id INTEGER,
  summary TEXT NOT NULL DEFAULT '',
  details TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_at ON audit_log(at);

CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT,
  updated_by INTEGER REFERENCES users(id)
);

CREATE TABLE site_content (
  key TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT '',
  updated_at TEXT,
  updated_by INTEGER REFERENCES users(id)
);

CREATE TABLE services (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT '',
  default_duration_min INTEGER NOT NULL DEFAULT 30,
  default_price_cents INTEGER,
  bookable_online INTEGER NOT NULL DEFAULT 1,
  active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0
);

-- Duration overrides: most specific match wins (dentist+branch > dentist > branch > service default).
CREATE TABLE service_durations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  service_id INTEGER NOT NULL REFERENCES services(id),
  branch_id INTEGER REFERENCES branches(id),
  dentist_id INTEGER REFERENCES users(id),
  minutes INTEGER NOT NULL
);

-- weekday: 0 = Monday ... 6 = Sunday
CREATE TABLE branch_hours (
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  weekday INTEGER NOT NULL,
  open_time TEXT NOT NULL DEFAULT '09:00',
  close_time TEXT NOT NULL DEFAULT '18:00',
  closed INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (branch_id, weekday)
);

CREATE TABLE resources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'chair',
  active INTEGER NOT NULL DEFAULT 1
);

-- Associate dentist schedules per branch and weekday.
CREATE TABLE dentist_schedules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dentist_id INTEGER NOT NULL REFERENCES users(id),
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  weekday INTEGER NOT NULL,
  start_time TEXT NOT NULL,
  end_time TEXT NOT NULL
);

CREATE TABLE gallery_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  caption TEXT NOT NULL DEFAULT '',
  image_path TEXT NOT NULL DEFAULT '',
  authorization_note TEXT NOT NULL DEFAULT '',
  authorized INTEGER NOT NULL DEFAULT 0,
  published INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE testimonials (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  quote TEXT NOT NULL,
  attribution TEXT NOT NULL DEFAULT '',
  consent_note TEXT NOT NULL DEFAULT '',
  approved INTEGER NOT NULL DEFAULT 0,
  published INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE patients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chart_no TEXT NOT NULL UNIQUE,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  birth_date TEXT,
  sex TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '',
  address TEXT NOT NULL DEFAULT '',
  preferred_branch_id INTEGER REFERENCES branches(id),
  alert_flag TEXT NOT NULL DEFAULT '',
  consent_privacy INTEGER NOT NULL DEFAULT 0,
  consent_privacy_at TEXT,
  consent_marketing INTEGER NOT NULL DEFAULT 0,
  contact_sms INTEGER NOT NULL DEFAULT 0,
  contact_email INTEGER NOT NULL DEFAULT 0,
  contact_messenger INTEGER NOT NULL DEFAULT 0,
  opt_out_all INTEGER NOT NULL DEFAULT 0,
  preferred_channel TEXT NOT NULL DEFAULT '',
  admin_notes TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  created_by INTEGER REFERENCES users(id),
  updated_at TEXT
);
CREATE INDEX idx_patients_name ON patients(last_name, first_name);

CREATE TABLE patient_assignments (
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  dentist_id INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  created_by INTEGER REFERENCES users(id),
  PRIMARY KEY (patient_id, dentist_id)
);

CREATE TABLE patient_history (
  patient_id INTEGER PRIMARY KEY REFERENCES patients(id),
  medical_conditions TEXT NOT NULL DEFAULT '',
  allergies TEXT NOT NULL DEFAULT '',
  medications TEXT NOT NULL DEFAULT '',
  dental_history TEXT NOT NULL DEFAULT '',
  other_notes TEXT NOT NULL DEFAULT '',
  updated_at TEXT,
  updated_by INTEGER REFERENCES users(id)
);

CREATE TABLE appointments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  service_id INTEGER NOT NULL REFERENCES services(id),
  dentist_id INTEGER REFERENCES users(id),
  resource_id INTEGER REFERENCES resources(id),
  start_at TEXT NOT NULL,
  end_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('requested','confirmed','checked_in','completed','cancelled','no_show')),
  source TEXT NOT NULL DEFAULT 'staff',
  internal_notes TEXT NOT NULL DEFAULT '',
  cancel_reason TEXT NOT NULL DEFAULT '',
  booking_request_id INTEGER,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT,
  checked_in_at TEXT,
  completed_at TEXT
);
CREATE INDEX idx_appt_branch_start ON appointments(branch_id, start_at);
CREATE INDEX idx_appt_dentist_start ON appointments(dentist_id, start_at);
CREATE INDEX idx_appt_patient ON appointments(patient_id);

CREATE TABLE booking_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ref_code TEXT NOT NULL UNIQUE,
  full_name TEXT NOT NULL,
  phone TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '',
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  service_id INTEGER NOT NULL REFERENCES services(id),
  dentist_id INTEGER REFERENCES users(id),
  preferred_start TEXT NOT NULL,
  message TEXT NOT NULL DEFAULT '',
  consent_privacy INTEGER NOT NULL DEFAULT 0,
  consent_contact INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','confirmed','declined','cancelled')),
  decline_reason TEXT NOT NULL DEFAULT '',
  handled_by INTEGER REFERENCES users(id),
  handled_at TEXT,
  appointment_id INTEGER REFERENCES appointments(id),
  patient_id INTEGER REFERENCES patients(id),
  created_at TEXT NOT NULL
);

CREATE TABLE clinical_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  appointment_id INTEGER REFERENCES appointments(id),
  author_id INTEGER NOT NULL REFERENCES users(id),
  body TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT,
  amended INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE procedures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  appointment_id INTEGER REFERENCES appointments(id),
  service_id INTEGER REFERENCES services(id),
  branch_id INTEGER REFERENCES branches(id),
  tooth TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('planned','completed')),
  performed_by INTEGER REFERENCES users(id),
  performed_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE treatment_plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  dentist_id INTEGER REFERENCES users(id),
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','presented','accepted','in_progress','completed','declined')),
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT
);

CREATE TABLE treatment_plan_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id INTEGER NOT NULL REFERENCES treatment_plans(id),
  service_id INTEGER REFERENCES services(id),
  tooth TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL,
  estimate_cents INTEGER,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','scheduled','done','declined')),
  seq INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE patient_documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  category TEXT NOT NULL DEFAULT 'other',
  clinical INTEGER NOT NULL DEFAULT 1,
  original_name TEXT NOT NULL,
  stored_name TEXT NOT NULL UNIQUE,
  mime TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  uploaded_by INTEGER REFERENCES users(id),
  uploaded_at TEXT NOT NULL
);

CREATE TABLE leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name TEXT NOT NULL,
  phone TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT 'other',
  branch_id INTEGER REFERENCES branches(id),
  service_id INTEGER REFERENCES services(id),
  message TEXT NOT NULL DEFAULT '',
  owner_id INTEGER REFERENCES users(id),
  status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','contacted','qualified','booked','converted','lost')),
  next_follow_up_at TEXT,
  lost_reason TEXT NOT NULL DEFAULT '',
  consent_contact INTEGER NOT NULL DEFAULT 0,
  patient_id INTEGER REFERENCES patients(id),
  appointment_id INTEGER REFERENCES appointments(id),
  created_at TEXT NOT NULL,
  created_by INTEGER REFERENCES users(id),
  updated_at TEXT
);

CREATE TABLE lead_activities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id INTEGER NOT NULL REFERENCES leads(id),
  user_id INTEGER REFERENCES users(id),
  kind TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE message_templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  purpose TEXT NOT NULL CHECK (purpose IN ('appointment_reminder','follow_up','lead_reply','booking_ack')),
  channel TEXT NOT NULL DEFAULT 'any',
  body TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT,
  updated_by INTEGER REFERENCES users(id)
);

CREATE TABLE reminder_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  purpose TEXT NOT NULL CHECK (purpose IN ('appointment','follow_up')),
  offset_minutes INTEGER NOT NULL,
  template_id INTEGER NOT NULL REFERENCES message_templates(id),
  channel TEXT NOT NULL DEFAULT 'sms',
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE follow_ups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  branch_id INTEGER REFERENCES branches(id),
  patient_id INTEGER REFERENCES patients(id),
  lead_id INTEGER REFERENCES leads(id),
  appointment_id INTEGER REFERENCES appointments(id),
  kind TEXT NOT NULL DEFAULT 'other',
  title TEXT NOT NULL,
  due_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','cancelled')),
  assignee_id INTEGER REFERENCES users(id),
  notes TEXT NOT NULL DEFAULT '',
  outcome TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  created_by INTEGER REFERENCES users(id),
  completed_at TEXT,
  completed_by INTEGER REFERENCES users(id)
);
CREATE INDEX idx_followups_due ON follow_ups(status, due_at);

CREATE TABLE reminders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER REFERENCES patients(id),
  appointment_id INTEGER REFERENCES appointments(id),
  follow_up_id INTEGER REFERENCES follow_ups(id),
  rule_id INTEGER REFERENCES reminder_rules(id),
  branch_id INTEGER REFERENCES branches(id),
  channel TEXT NOT NULL,
  template_id INTEGER REFERENCES message_templates(id),
  scheduled_for TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sent_manual','sent_provider','skipped_opt_out','skipped_no_consent','failed','cancelled')),
  rendered_body TEXT NOT NULL DEFAULT '',
  provider TEXT NOT NULL DEFAULT 'manual',
  result_note TEXT NOT NULL DEFAULT '',
  sent_at TEXT,
  sent_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_reminder_unique ON reminders(appointment_id, rule_id);

CREATE TABLE invoice_sequences (
  branch_id INTEGER PRIMARY KEY REFERENCES branches(id),
  prefix TEXT NOT NULL,
  next_no INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  number TEXT UNIQUE,
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  appointment_id INTEGER REFERENCES appointments(id),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','issued','void')),
  issued_at TEXT,
  subtotal_cents INTEGER NOT NULL DEFAULT 0,
  discount_cents INTEGER NOT NULL DEFAULT 0,
  tax_cents INTEGER NOT NULL DEFAULT 0,
  total_cents INTEGER NOT NULL DEFAULT 0,
  notes TEXT NOT NULL DEFAULT '',
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  voided_at TEXT,
  voided_by INTEGER REFERENCES users(id),
  void_reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_invoices_branch_issued ON invoices(branch_id, issued_at);

CREATE TABLE invoice_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  service_id INTEGER REFERENCES services(id),
  description TEXT NOT NULL,
  qty INTEGER NOT NULL DEFAULT 1,
  unit_price_cents INTEGER NOT NULL,
  discount_cents INTEGER NOT NULL DEFAULT 0,
  amount_cents INTEGER NOT NULL
);

CREATE TABLE payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL REFERENCES invoices(id),
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  kind TEXT NOT NULL DEFAULT 'payment' CHECK (kind IN ('payment','refund')),
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  method TEXT NOT NULL,
  reference TEXT NOT NULL DEFAULT '',
  received_at TEXT NOT NULL,
  received_by INTEGER REFERENCES users(id),
  status TEXT NOT NULL DEFAULT 'valid' CHECK (status IN ('valid','void')),
  notes TEXT NOT NULL DEFAULT '',
  void_reason TEXT NOT NULL DEFAULT '',
  voided_by INTEGER REFERENCES users(id),
  voided_at TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_payments_branch_date ON payments(branch_id, received_at);

CREATE TABLE employees (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER UNIQUE REFERENCES users(id),
  full_name TEXT NOT NULL,
  position TEXT NOT NULL DEFAULT '',
  employment_type TEXT NOT NULL DEFAULT 'regular',
  primary_branch_id INTEGER REFERENCES branches(id),
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE compensation (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  basis TEXT NOT NULL CHECK (basis IN ('monthly','daily','hourly','percentage','per_case','unset')),
  rate_cents INTEGER,
  percentage_bp INTEGER,
  notes TEXT NOT NULL DEFAULT '',
  effective_from TEXT NOT NULL,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);

CREATE TABLE time_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  work_date TEXT NOT NULL,
  time_in TEXT,
  time_out TEXT,
  source TEXT NOT NULL DEFAULT 'manual',
  status TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','exception','corrected','excused')),
  exception_note TEXT NOT NULL DEFAULT '',
  correction_reason TEXT NOT NULL DEFAULT '',
  corrected_by INTEGER REFERENCES users(id),
  corrected_at TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (employee_id, work_date)
);

CREATE TABLE payroll_periods (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  branch_id INTEGER REFERENCES branches(id),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','submitted','approved','cancelled')),
  rules_confirmed INTEGER NOT NULL DEFAULT 0,
  notes TEXT NOT NULL DEFAULT '',
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  submitted_by INTEGER REFERENCES users(id),
  submitted_at TEXT,
  approved_by INTEGER REFERENCES users(id),
  approved_at TEXT
);

CREATE TABLE payroll_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  period_id INTEGER NOT NULL REFERENCES payroll_periods(id),
  employee_id INTEGER NOT NULL REFERENCES employees(id),
  days_present INTEGER NOT NULL DEFAULT 0,
  minutes_worked INTEGER NOT NULL DEFAULT 0,
  late_minutes INTEGER NOT NULL DEFAULT 0,
  undertime_minutes INTEGER NOT NULL DEFAULT 0,
  open_exceptions INTEGER NOT NULL DEFAULT 0,
  basis TEXT NOT NULL DEFAULT 'unset',
  rate_cents INTEGER,
  percentage_bp INTEGER,
  estimate_cents INTEGER,
  adjustment_cents INTEGER NOT NULL DEFAULT 0,
  adjustment_note TEXT NOT NULL DEFAULT '',
  UNIQUE (period_id, employee_id)
);

CREATE TABLE report_cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  branch_id INTEGER REFERENCES branches(id),
  period_from TEXT NOT NULL,
  period_to TEXT NOT NULL,
  reviewer_id INTEGER REFERENCES users(id),
  status TEXT NOT NULL DEFAULT 'pending_review' CHECK (status IN ('pending_review','approved','changes_requested','revoked')),
  summary TEXT NOT NULL DEFAULT '',
  recommendations TEXT NOT NULL DEFAULT '',
  snapshot TEXT NOT NULL DEFAULT '{}',
  generated_by INTEGER REFERENCES users(id),
  generated_at TEXT NOT NULL,
  reviewed_by INTEGER REFERENCES users(id),
  reviewed_at TEXT,
  review_note TEXT NOT NULL DEFAULT ''
);
