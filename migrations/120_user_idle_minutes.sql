-- Each staff member picks how long the system waits with no activity before signing them out (NULL = the clinic default).
ALTER TABLE users ADD COLUMN idle_minutes INTEGER
