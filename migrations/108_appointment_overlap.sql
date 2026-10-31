-- Staff may double-book a dentist or chair on purpose (e.g. 10:00-10:30 and 10:20-11:00); remembered so confirming later doesn't block it.
ALTER TABLE appointments ADD COLUMN overlap_ok INTEGER NOT NULL DEFAULT 0
