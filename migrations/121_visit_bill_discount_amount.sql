-- A progress note's bill discount can be a peso amount instead of a percent (NULL or 0 = use the percent).
ALTER TABLE visit_notes ADD COLUMN bill_discount_cents INTEGER
