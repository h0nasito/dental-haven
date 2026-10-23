-- Faster lookups of a bill's lines and payments (bill pages, reports, and removing converted MyMedsPH bills).
CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice ON invoice_items(invoice_id);
CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments(invoice_id);
