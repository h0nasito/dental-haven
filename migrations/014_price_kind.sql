-- How a price is stated: 'fixed' (₱650), 'from' (₱980 minimum), or a range (from/to both set). Plus a short note.
ALTER TABLE price_items ADD COLUMN kind TEXT NOT NULL DEFAULT 'from';
