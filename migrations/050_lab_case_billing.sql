-- The lab bills the branches for their lab cases: each branch is a lab client, and lab invoices can hold branch cases.
ALTER TABLE lab_clients ADD COLUMN branch_id INTEGER REFERENCES branches(id);
ALTER TABLE lab_invoice_items ADD COLUMN case_id INTEGER REFERENCES lab_cases(id);
ALTER TABLE lab_cases ADD COLUMN invoice_id INTEGER REFERENCES lab_invoices(id)
