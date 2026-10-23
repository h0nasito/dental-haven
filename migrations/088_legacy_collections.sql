-- Payments brought in from MyMedsPH collection reports: a fingerprint so uploading the same report again adds nothing,
-- and the dentist / procedures the report gives for the payment (kept as text for reference).
ALTER TABLE payments ADD COLUMN legacy_key TEXT;
ALTER TABLE patient_credits ADD COLUMN legacy_key TEXT;
CREATE INDEX idx_payments_legacy_key ON payments(legacy_key);
CREATE INDEX idx_patient_credits_legacy_key ON patient_credits(legacy_key);
ALTER TABLE invoice_items ADD COLUMN legacy_dentist INTEGER NOT NULL DEFAULT 0;
