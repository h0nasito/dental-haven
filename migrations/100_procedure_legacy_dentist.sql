-- Imported MyMedsPH visits get their dentist from the bill of that day (billing report); 1 = set that way (Undo clears it).
ALTER TABLE procedures ADD COLUMN legacy_dentist INTEGER NOT NULL DEFAULT 0
