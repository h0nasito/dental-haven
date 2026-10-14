-- One staff group chat (text only). Messages older than a year are deleted automatically.
CREATE TABLE chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  body TEXT NOT NULL,
  created_at TEXT NOT NULL,
  deleted_at TEXT,
  deleted_by INTEGER REFERENCES users(id)
);
CREATE INDEX idx_chat_messages_created ON chat_messages(created_at);
CREATE TABLE chat_reads (
  user_id INTEGER PRIMARY KEY REFERENCES users(id),
  last_read_id INTEGER NOT NULL DEFAULT 0
);
