-- X-ray cash is deposited separately from the clinic's: each bank deposit belongs to a fund ('clinic' or 'xray').
ALTER TABLE cash_deposits ADD COLUMN fund TEXT NOT NULL DEFAULT 'clinic'
