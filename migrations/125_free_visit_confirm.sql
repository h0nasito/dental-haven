-- ₱0 bills (e.g. a braces adjustment paid in the package): the patient signs to confirm the visit, without a payment.
ALTER TABLE invoices ADD COLUMN confirmed_signature_id INTEGER REFERENCES payment_signatures(id);
ALTER TABLE invoices ADD COLUMN confirmed_at TEXT;
ALTER TABLE invoices ADD COLUMN confirmed_by INTEGER REFERENCES users(id)
