-- Profile pictures: a small square JPEG per user (stored outside the web root).
ALTER TABLE users ADD COLUMN avatar TEXT;
