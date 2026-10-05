-- Written progress notes can be removed by a super admin (with a reason). The row is kept, hidden, so a MyMedsPH
-- re-import doesn't bring it back and the audit trail keeps the original text.
ALTER TABLE clinical_notes ADD COLUMN deleted_at TEXT;
ALTER TABLE clinical_notes ADD COLUMN deleted_by INTEGER REFERENCES users(id);
ALTER TABLE clinical_notes ADD COLUMN deleted_reason TEXT NOT NULL DEFAULT ''
