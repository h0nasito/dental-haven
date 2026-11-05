-- An employee may undo their own time out within a few minutes (pressed by mistake); the punch is kept and marked undone.
ALTER TABLE time_punches ADD COLUMN undone_at TEXT
