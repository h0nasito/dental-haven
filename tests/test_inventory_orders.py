"""Monthly order lists: start (pre-filled with low stock), add items, submit, return, approve, order, receive into stock."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestInventoryOrders(Base):
    def setUp(self):
        super().setUp()
        from app.util import now_str
        self.loc = self.q("SELECT * FROM inventory_locations WHERE branch_id = ? LIMIT 1", (self.branch("malolos"),))
        self.item = self.q("SELECT * FROM inventory_items WHERE active = 1 ORDER BY id LIMIT 1")
        self.conn.execute("DELETE FROM inventory_stock WHERE location_id = ? AND item_id = ?", (self.loc["id"], self.item["id"]))
        self.conn.execute("INSERT INTO inventory_stock (location_id, item_id, qty, reorder_level, updated_at) VALUES (?, ?, 2, 5, ?)",
                          (self.loc["id"], self.item["id"], now_str()))
        self.conn.execute("UPDATE inventory_orders SET status = 'cancelled'")
        self.month = f"2030-{(id(self) % 12) + 1:02d}"

    def start(self, c):
        r = c.post("/staff/inventory/orders", data={"location_id": self.loc["id"], "for_month": self.month})
        self.assertEqual(r.status_code, 302, r.data[:300])
        return int(r.headers["Location"].rstrip("/").split("/")[-1])

    def test_full_flow(self):
        staff = self.login("staff.malolos")
        oid = self.start(staff)
        line = self.q("SELECT * FROM inventory_order_lines WHERE order_id = ? AND item_id = ?", (oid, self.item["id"]))
        self.assertEqual(line["qty"], 8)                    # back to 2 x reorder level (10) - 2 in stock
        # same branch + month again goes to the existing list
        self.assertEqual(self.start(staff), oid)
        staff.post(f"/staff/inventory/orders/{oid}", data={"action": "add", "item": "Special bur (demo)", "qty": "3", "unit": "piece", "price": "150"})
        free = self.q("SELECT * FROM inventory_order_lines WHERE order_id = ? AND item_id IS NULL", (oid,))
        self.assertEqual((free["qty"], free["unit_price_cents"]), (3, 15000))
        staff.post(f"/staff/inventory/orders/{oid}", data={"action": "submit", f"qty_{line['id']}": "10", f"note_{line['id']}": "x"})
        o = self.q("SELECT * FROM inventory_orders WHERE id = ?", (oid,))
        self.assertEqual(o["status"], "submitted")
        self.assertEqual(self.q("SELECT qty FROM inventory_order_lines WHERE id = ?", (line["id"],))["qty"], 10)
        # staff can't approve
        self.assertEqual(staff.post(f"/staff/inventory/orders/{oid}", data={"action": "approve"}).status_code, 403)
        admin = self.login("admin")
        admin.post(f"/staff/inventory/orders/{oid}", data={"action": "return", "review_note": "Too many"})
        self.assertEqual(self.q("SELECT status FROM inventory_orders WHERE id = ?", (oid,))["status"], "draft")
        staff.post(f"/staff/inventory/orders/{oid}", data={"action": "submit"})
        admin.post(f"/staff/inventory/orders/{oid}", data={"action": "approve", f"approved_{line['id']}": "6"})
        self.assertEqual(self.q("SELECT approved_qty FROM inventory_order_lines WHERE id = ?", (line["id"],))["approved_qty"], 6)
        admin.post(f"/staff/inventory/orders/{oid}", data={"action": "ordered"})
        admin.post(f"/staff/inventory/orders/{oid}", data={"action": "receive", f"received_{line['id']}": "5", f"received_{free['id']}": "3"})
        self.assertEqual(self.q("SELECT status FROM inventory_orders WHERE id = ?", (oid,))["status"], "received")
        self.assertEqual(self.q("SELECT qty FROM inventory_stock WHERE location_id = ? AND item_id = ?", (self.loc["id"], self.item["id"]))["qty"], 7)
        self.assertIsNotNone(self.q("SELECT id FROM inventory_moves WHERE item_id = ? AND kind = 'received' AND note LIKE 'Order list #%'", (self.item["id"],)))
        self.assertIn("Order list", admin.get(f"/staff/inventory/orders/{oid}/print").data.decode())
        # voiding a received list (super admin / "Void inventory order approval") takes the stock back out; staff can't
        self.assertEqual(staff.post(f"/staff/inventory/orders/{oid}", data={"action": "void", "void_reason": "mistake"}).status_code, 403)
        self.assertIn("Void order list", admin.get(f"/staff/inventory/orders/{oid}").data.decode())
        admin.post(f"/staff/inventory/orders/{oid}", data={"action": "void", "void_reason": ""})
        self.assertEqual(self.q("SELECT status FROM inventory_orders WHERE id = ?", (oid,))["status"], "received")   # reason needed
        admin.post(f"/staff/inventory/orders/{oid}", data={"action": "void", "void_reason": "Received twice by mistake"})
        self.assertEqual(self.q("SELECT status FROM inventory_orders WHERE id = ?", (oid,))["status"], "cancelled")
        self.assertEqual(self.q("SELECT qty FROM inventory_stock WHERE location_id = ? AND item_id = ?", (self.loc["id"], self.item["id"]))["qty"], 2)

    def test_undo_approval(self):
        staff = self.login("staff.malolos")
        oid = self.start(staff)
        staff.post(f"/staff/inventory/orders/{oid}", data={"action": "submit"})
        admin = self.login("admin")
        admin.post(f"/staff/inventory/orders/{oid}", data={"action": "approve"})
        admin.post(f"/staff/inventory/orders/{oid}", data={"action": "ordered"})
        admin.post(f"/staff/inventory/orders/{oid}", data={"action": "unapprove", "void_reason": "Approved by mistake"})
        o = self.q("SELECT * FROM inventory_orders WHERE id = ?", (oid,))
        self.assertEqual((o["status"], o["approved_by"]), ("submitted", None))
        self.assertIn("Approved by mistake", o["review_note"])
        # a person given the permission can do it
        from app.util import now_str
        uid = self.q("SELECT id FROM users WHERE email LIKE 'staff.malolos@%'")["id"]
        admin.post(f"/staff/inventory/orders/{oid}", data={"action": "approve"})
        self.conn.execute("INSERT INTO user_permissions (user_id, permission, granted) VALUES (?, 'inventory.order_void', 1)", (uid,))
        self.login("staff.malolos").post(f"/staff/inventory/orders/{oid}", data={"action": "unapprove", "void_reason": "Wrong items"})
        self.assertEqual(self.q("SELECT status FROM inventory_orders WHERE id = ?", (oid,))["status"], "submitted")
        self.conn.execute("DELETE FROM user_permissions WHERE user_id = ?", (uid,))

    def test_access(self):
        d = self.login("dentist.malolos")
        self.assertEqual(d.get("/staff/inventory/orders").status_code, 403)
        self.assertEqual(self.login("staff.malolos").get("/staff/inventory/orders").status_code, 200)

    def test_reminder_before_month_end(self):
        from datetime import date
        from unittest import mock
        from app.views import inventory_orders as io
        with self.app.app_context(), mock.patch.object(io, "today", return_value=date(2031, 1, 28)):
            from app.db import get_db
            n = io.run_reminders(get_db())
            self.assertGreaterEqual(n, 1)
            self.assertEqual(io.run_reminders(get_db()), 0)   # once per branch per month
        self.assertIsNotNone(self.q("SELECT id FROM notifications WHERE kind = 'inventory_order_due'"))
        with self.app.app_context(), mock.patch.object(io, "today", return_value=date(2031, 3, 10)):
            from app.db import get_db
            self.assertEqual(io.run_reminders(get_db()), 0)   # not yet near month end
