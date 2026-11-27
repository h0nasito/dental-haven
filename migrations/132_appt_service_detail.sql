-- The specific procedure of an appointment in everyday words (e.g. "Braces adjustment", "Bunot (tooth extraction)"), shown on the calendar.
ALTER TABLE appointments ADD COLUMN service_detail TEXT NOT NULL DEFAULT ''
