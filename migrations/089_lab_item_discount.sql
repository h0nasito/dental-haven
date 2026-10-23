-- A discount per item on an outside lab work: the amount taken off that item, and the % when it was typed as a percentage.
ALTER TABLE lab_work_items ADD COLUMN discount_cents INTEGER NOT NULL DEFAULT 0;
ALTER TABLE lab_work_items ADD COLUMN discount_bp INTEGER;
