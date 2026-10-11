-- Laboratory payments: which bank account or e-wallet the clinic paid into.
ALTER TABLE lab_payments ADD COLUMN account TEXT NOT NULL DEFAULT '';
UPDATE lab_payments SET account = 'GCash' WHERE method = 'gcash';
