-- Photos for a photo-led website: one per service, one per branch, and page photos (hero, lab).
ALTER TABLE services ADD COLUMN image_path TEXT NOT NULL DEFAULT '';
ALTER TABLE branches ADD COLUMN image_path TEXT NOT NULL DEFAULT '';
CREATE TABLE site_images (
  key TEXT PRIMARY KEY,
  image_path TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL,
  updated_by INTEGER REFERENCES users(id)
);
