-- Replies in the group chat: a message can quote the message it answers.
ALTER TABLE chat_messages ADD COLUMN reply_to_id INTEGER REFERENCES chat_messages(id);
