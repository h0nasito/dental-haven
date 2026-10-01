-- Staff evaluation forms (e.g. the Assistant Checklist). The admin opens and closes each form; only signed-in
-- accounts whose access role has "Answer evaluation forms" can answer, through the form's link.
CREATE TABLE evaluation_forms (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  questions_json TEXT NOT NULL DEFAULT '[]',
  allow_na INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'closed' CHECK (status IN ('open','closed')),
  opened_at TEXT,
  closed_at TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT
);
CREATE TABLE evaluation_responses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  form_id INTEGER NOT NULL REFERENCES evaluation_forms(id),
  evaluator_id INTEGER NOT NULL REFERENCES users(id),
  subject_employee_id INTEGER REFERENCES employees(id),
  branch_id INTEGER REFERENCES branches(id),
  eval_date TEXT NOT NULL,
  answers_json TEXT NOT NULL DEFAULT '{}',
  yes_count INTEGER NOT NULL DEFAULT 0,
  no_count INTEGER NOT NULL DEFAULT 0,
  na_count INTEGER NOT NULL DEFAULT 0,
  remarks TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'valid' CHECK (status IN ('valid','deleted')),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_eval_responses_form ON evaluation_responses(form_id, eval_date)
