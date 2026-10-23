-- Website messages that look like spam are kept but set aside (Leads > Spam), with the reason.
ALTER TABLE leads ADD COLUMN spam INTEGER NOT NULL DEFAULT 0;
ALTER TABLE leads ADD COLUMN spam_reason TEXT NOT NULL DEFAULT '';
CREATE INDEX idx_leads_spam ON leads(spam, status);
