-- Google rating shown on the website for each branch, entered by staff from the branch's Google Business Profile.
ALTER TABLE branches ADD COLUMN google_reviews_url TEXT NOT NULL DEFAULT '';
ALTER TABLE branches ADD COLUMN google_rating REAL;
ALTER TABLE branches ADD COLUMN google_review_count INTEGER;
ALTER TABLE branches ADD COLUMN google_rating_as_of TEXT
