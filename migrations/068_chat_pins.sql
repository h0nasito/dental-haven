-- Pinned group chat messages (pinned by the admin, HR or a supervisor).
ALTER TABLE chat_messages ADD COLUMN pinned_at TEXT;
ALTER TABLE chat_messages ADD COLUMN pinned_by INTEGER REFERENCES users(id);
