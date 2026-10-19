-- Clinic and laboratory inventories are separate: each item belongs to the clinic list or the laboratory list.
-- Branch locations show clinic items; the laboratory's location shows laboratory items. Existing items are clinic items,
-- except items that only ever had stock at the laboratory, which move to the laboratory list.
ALTER TABLE inventory_items ADD COLUMN scope TEXT NOT NULL DEFAULT 'clinic' CHECK (scope IN ('clinic', 'lab'));
CREATE INDEX idx_inventory_items_scope ON inventory_items(scope, active);
UPDATE inventory_items SET scope = 'lab'
WHERE id IN (SELECT s.item_id FROM inventory_stock s JOIN inventory_locations l ON l.id = s.location_id WHERE l.laboratory_id IS NOT NULL)
  AND id NOT IN (SELECT s.item_id FROM inventory_stock s JOIN inventory_locations l ON l.id = s.location_id WHERE l.laboratory_id IS NULL)
