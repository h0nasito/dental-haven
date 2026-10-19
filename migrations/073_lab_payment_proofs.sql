-- Lab payments: proof of payment (photo of a GCash/bank transfer screenshot, deposit slip, cheque; or a PDF). Up to 4 per payment.
CREATE TABLE lab_payment_proofs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  payment_id INTEGER NOT NULL REFERENCES lab_payments(id),
  stored_name TEXT NOT NULL,
  uploaded_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_lab_payment_proofs ON lab_payment_proofs(payment_id)
