-- Lab invoice lines: "Less" lines (deductions such as a free unit) shown as negative amounts.
ALTER TABLE lab_invoice_items ADD COLUMN is_less INTEGER NOT NULL DEFAULT 0
