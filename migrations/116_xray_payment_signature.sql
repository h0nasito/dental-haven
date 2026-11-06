-- X-ray payments carry the patient's signature (like bill payments), or the reason they couldn't sign.
ALTER TABLE xray_payments ADD COLUMN signature_name TEXT NOT NULL DEFAULT '';
ALTER TABLE xray_payments ADD COLUMN not_signed_reason TEXT NOT NULL DEFAULT ''
