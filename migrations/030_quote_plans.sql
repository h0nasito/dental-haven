-- Treatment plan quotations like the clinic's design: plans (Plan A recommended / Plan B), sections, material options
-- (choose one, not added together), freebies (value shown, not charged), price unit labels and red notes per line.
ALTER TABLE quotation_items ADD COLUMN plan TEXT NOT NULL DEFAULT '';
ALTER TABLE quotation_items ADD COLUMN section TEXT NOT NULL DEFAULT '';
ALTER TABLE quotation_items ADD COLUMN kind TEXT NOT NULL DEFAULT 'item';
ALTER TABLE quotation_items ADD COLUMN unit_label TEXT NOT NULL DEFAULT '';
ALTER TABLE quotation_items ADD COLUMN note TEXT NOT NULL DEFAULT '';
ALTER TABLE quotations ADD COLUMN recommended_plan TEXT NOT NULL DEFAULT '';
ALTER TABLE quotations ADD COLUMN prepared_by TEXT NOT NULL DEFAULT ''
