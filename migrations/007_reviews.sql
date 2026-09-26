-- Patient reviews on the website: optional star rating, where the review came from, and the branch.
ALTER TABLE testimonials ADD COLUMN rating INTEGER;
ALTER TABLE testimonials ADD COLUMN source TEXT NOT NULL DEFAULT '';
ALTER TABLE testimonials ADD COLUMN branch_id INTEGER REFERENCES branches(id);
