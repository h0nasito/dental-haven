-- X-rays are their own section: X-ray lines typed on patient bills (e.g. PANORAMIC XRAY) are left out of the clinic's collection reports.
-- NULL = not checked yet (the app sets 1 or 0 from the description); a changed description is checked again.
ALTER TABLE invoice_items ADD COLUMN xray INTEGER;
CREATE TRIGGER trg_invoice_items_xray_recheck AFTER UPDATE OF description ON invoice_items WHEN NEW.description IS NOT OLD.description BEGIN UPDATE invoice_items SET xray = NULL WHERE id = NEW.id; END
