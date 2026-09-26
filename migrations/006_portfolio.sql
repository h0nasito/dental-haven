-- Portfolio on the landing page: filter by category, optional "before" photo for a before/after slider.
ALTER TABLE gallery_items ADD COLUMN category TEXT NOT NULL DEFAULT '';
ALTER TABLE gallery_items ADD COLUMN before_image_path TEXT NOT NULL DEFAULT '';
ALTER TABLE gallery_items ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0;
