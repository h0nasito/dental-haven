-- Procedures recorded outside the progress note form (Generate progress note from a treatment plan, Record procedure)
-- also wait for a bill: their price (from the plan item or the fee schedule), and the bill they went on.
ALTER TABLE procedures ADD COLUMN price_cents INTEGER;
ALTER TABLE procedures ADD COLUMN invoice_id INTEGER REFERENCES invoices(id);
ALTER TABLE procedures ADD COLUMN bill_skipped_at TEXT;
ALTER TABLE procedures ADD COLUMN bill_skipped_by INTEGER REFERENCES users(id)
