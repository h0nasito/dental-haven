-- MyMedsPH bills turned into real bills: each old bill line points to the bill it became; those bills and their
-- "paid in MyMedsPH" payments are marked so the conversion can be undone.
ALTER TABLE legacy_bills ADD COLUMN invoice_id INTEGER REFERENCES invoices(id);
ALTER TABLE invoices ADD COLUMN legacy INTEGER NOT NULL DEFAULT 0;
CREATE INDEX idx_legacy_bills_invoice ON legacy_bills(invoice_id);
