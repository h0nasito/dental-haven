-- The employee's own reason for overtime (what they worked on), given at time out or later; the approver sees it.
ALTER TABLE time_records ADD COLUMN ot_reason TEXT NOT NULL DEFAULT ''
