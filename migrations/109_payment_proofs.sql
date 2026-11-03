-- Proof of payment (GCash / Maya / bank transfer screenshot, card slip, check photo): pictures or PDFs kept privately, linked to the payment.
CREATE TABLE payment_proofs (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    payment_id INTEGER REFERENCES payments(id),
    stored_name TEXT NOT NULL,
    uploaded_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE INDEX idx_payment_proofs_payment ON payment_proofs(payment_id);
CREATE INDEX idx_payment_proofs_invoice ON payment_proofs(invoice_id)
