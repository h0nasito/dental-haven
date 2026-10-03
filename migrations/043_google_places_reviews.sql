-- Google reviews fetched automatically through the Google Places API (only when GOOGLE_PLACES_API_KEY is set).
ALTER TABLE branches ADD COLUMN google_place_id TEXT NOT NULL DEFAULT '';
ALTER TABLE branches ADD COLUMN google_synced_at TEXT;
ALTER TABLE branches ADD COLUMN google_sync_error TEXT NOT NULL DEFAULT '';
CREATE TABLE google_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  branch_id INTEGER NOT NULL REFERENCES branches(id),
  author_name TEXT NOT NULL DEFAULT '',
  author_uri TEXT NOT NULL DEFAULT '',
  author_photo TEXT NOT NULL DEFAULT '',
  rating INTEGER,
  text TEXT NOT NULL DEFAULT '',
  relative_time TEXT NOT NULL DEFAULT '',
  publish_time TEXT NOT NULL DEFAULT '',
  review_uri TEXT NOT NULL DEFAULT '',
  sort_order INTEGER NOT NULL DEFAULT 0,
  fetched_at TEXT NOT NULL
);
CREATE INDEX idx_google_reviews_branch ON google_reviews(branch_id, sort_order)
