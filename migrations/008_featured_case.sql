-- One gallery case can be featured at the top of the home page (before/after slider).
ALTER TABLE gallery_items ADD COLUMN featured INTEGER NOT NULL DEFAULT 0;
