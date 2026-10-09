-- Where each payment went: the bank account (BDO, BPI, ...) or e-wallet it was paid into.
ALTER TABLE payments ADD COLUMN account TEXT NOT NULL DEFAULT '';
ALTER TABLE patient_credits ADD COLUMN account TEXT NOT NULL DEFAULT '';
UPDATE payments SET account = 'GCash' WHERE method = 'gcash';
UPDATE patient_credits SET account = 'GCash' WHERE method = 'gcash';
