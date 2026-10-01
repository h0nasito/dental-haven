-- Contact mobile and (for dentists) specialization on user accounts, shown in Users → Associates / Staff.
ALTER TABLE users ADD COLUMN mobile TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN specialization TEXT NOT NULL DEFAULT ''
