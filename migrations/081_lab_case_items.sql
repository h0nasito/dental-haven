-- One branch lab case (one patient) can hold several items, e.g. 2 units E.max crown on 11, 12 + 3 units zirconia bridge on 23-25.
-- lab_cases keeps a summary (case type text, total units, total lab price) for lists; each item is a row here and a line on the lab invoice.
CREATE TABLE lab_case_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL REFERENCES lab_cases(id),
  case_type TEXT NOT NULL,
  units INTEGER NOT NULL DEFAULT 1,
  teeth TEXT NOT NULL DEFAULT '',
  shade TEXT NOT NULL DEFAULT '',
  material TEXT NOT NULL DEFAULT '',
  lab_fee_cents INTEGER,
  instructions TEXT NOT NULL DEFAULT '',
  sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_lab_case_items ON lab_case_items(case_id, sort_order);
INSERT INTO lab_case_items (case_id, case_type, units, teeth, shade, material, lab_fee_cents, instructions, sort_order)
  SELECT id, case_type, COALESCE(units, 1), teeth, shade, material, lab_fee_cents, '', 0 FROM lab_cases;
ALTER TABLE lab_invoice_items ADD COLUMN case_item_id INTEGER REFERENCES lab_case_items(id);
UPDATE lab_invoice_items SET case_item_id = (SELECT i.id FROM lab_case_items i WHERE i.case_id = lab_invoice_items.case_id) WHERE case_id IS NOT NULL;
