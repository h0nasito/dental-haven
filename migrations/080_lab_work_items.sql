-- One outside work (one patient, one number) can hold several items, e.g. 2 units E.max veneer + 3 units zirconia bridge.
-- lab_works keeps a summary (case type text, total units) for lists; each item is a row here and a line on the invoice.
CREATE TABLE lab_work_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  work_id INTEGER NOT NULL REFERENCES lab_works(id),
  case_type TEXT NOT NULL,
  units INTEGER NOT NULL DEFAULT 1,
  arch TEXT NOT NULL DEFAULT '',
  teeth TEXT NOT NULL DEFAULT '',
  shade TEXT NOT NULL DEFAULT '',
  material TEXT NOT NULL DEFAULT '',
  price_cents INTEGER,
  instructions TEXT NOT NULL DEFAULT '',
  sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_lab_work_items ON lab_work_items(work_id, sort_order);
INSERT INTO lab_work_items (work_id, case_type, units, arch, teeth, shade, material, price_cents, instructions, sort_order)
  SELECT id, case_type, units, arch, teeth, shade, material, price_cents, '', 0 FROM lab_works
