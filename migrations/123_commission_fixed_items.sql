-- Which bill lines' fixed commission a commission entry paid (JSON {"item id": cents}), so each fixed amount is paid once.
ALTER TABLE dentist_commissions ADD COLUMN fixed_items TEXT NOT NULL DEFAULT ''
