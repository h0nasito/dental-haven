-- Branch lab cases: the branch confirms when the piece was installed in the patient; the lab is paid only for installed cases.
-- Cases on lab bills already paid in full were installed before this step existed, so they are marked installed.
ALTER TABLE lab_cases ADD COLUMN installed_on TEXT;
ALTER TABLE lab_cases ADD COLUMN installed_by INTEGER REFERENCES users(id);
UPDATE lab_cases SET installed_on = COALESCE(completed_on, substr(updated_at, 1, 10), sent_on) WHERE installed_on IS NULL AND invoice_id IN (SELECT id FROM lab_invoices WHERE status = 'issued' AND total_cents > 0 AND paid_cents >= total_cents)
