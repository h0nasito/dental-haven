-- Price-list items the dentist earns no commission on (e.g. asepsis fee): left out of the commission unless the bill line sets one.
ALTER TABLE fee_schedule ADD COLUMN no_commission INTEGER NOT NULL DEFAULT 0
