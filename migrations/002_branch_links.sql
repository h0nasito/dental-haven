-- Per-branch social and navigation links
ALTER TABLE branches ADD COLUMN facebook_url TEXT NOT NULL DEFAULT '';
ALTER TABLE branches ADD COLUMN waze_url TEXT NOT NULL DEFAULT '';
