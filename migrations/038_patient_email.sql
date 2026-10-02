-- Patient emails: birthday greetings and announcement / promotion blasts, sent from a queue a little at a time.
CREATE TABLE email_campaigns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL CHECK (kind IN ('announcement','promotion')),
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  branch_id INTEGER REFERENCES branches(id),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','queued','done','cancelled')),
  recipients INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  queued_at TEXT,
  updated_at TEXT
);

CREATE TABLE email_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL CHECK (kind IN ('birthday','announcement','promotion')),
  campaign_id INTEGER REFERENCES email_campaigns(id),
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  to_email TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  dedupe_key TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sending','sent','failed','cancelled')),
  sender TEXT NOT NULL DEFAULT '',
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  claimed_at TEXT,
  sent_at TEXT
);
CREATE INDEX idx_email_outbox_status ON email_outbox(status, id);
CREATE INDEX idx_email_outbox_sent ON email_outbox(sender, sent_at);

-- Patients can stop announcement / birthday emails (promotions use consent_marketing).
ALTER TABLE patients ADD COLUMN news_opt_out INTEGER NOT NULL DEFAULT 0;
