"""Inventory: who can see and update stock, per-location scope, counts, receiving, using, history and export."""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestInventory(Base):
    def loc(self, name_like):
        return self.q("SELECT * FROM inventory_locations WHERE name LIKE ?", (name_like,))

    def item(self, name):
        return self.q("SELECT * FROM inventory_items WHERE name = ?", (name,))

    def stock(self, loc_id, item_id):
        return self.q("SELECT * FROM inventory_stock WHERE location_id = ? AND item_id = ?", (loc_id, item_id))

    def test_items_and_locations_loaded(self):
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM inventory_items"), 592)
        names = [r["name"] for r in self.conn.all("SELECT name FROM inventory_locations ORDER BY sort_order")]
        self.assertEqual(len(names), 5)
        self.assertEqual(names[-1], "Digital Solutions Dental Laboratory")
        self.assertEqual(self.item("Cotton Roll")["category"], "Routine Disposables")
        self.assertEqual(self.item("Gutta Percha .04 F2 (Red)")["category"], "Endodontic (Root Canal)")
        self.assertEqual(self.item("Wire 18 NITI Upper")["category"], "Orthodontic")

    def test_only_super_admin_updates_by_default(self):
        # Staff can view their own branches only; receptionists can't see inventory at all.
        self.assertEqual(self.login("reception.malolos").get("/staff/inventory").status_code, 403)
        c = self.login("staff.malolos")
        page = c.get("/staff/inventory").data.decode()
        mal, boc, gui, lab = self.loc("Malolos%"), self.loc("Bocaue%"), self.loc("Guiguinto%"), self.loc("Digital%")
        self.assertIn(f'href="/staff/inventory/{mal["id"]}"', page)
        self.assertIn(f'href="/staff/inventory/{gui["id"]}"', page)
        self.assertNotIn(f'href="/staff/inventory/{boc["id"]}"', page)
        self.assertNotIn(f'href="/staff/inventory/{lab["id"]}"', page)
        self.assertEqual(c.get(f"/staff/inventory/{boc['id']}").status_code, 404)
        roll = self.item("Cotton Roll")
        before = self.stock(mal["id"], roll["id"])
        self.assertEqual(c.post(f"/staff/inventory/{mal['id']}", data={"category": "Routine Disposables", f"qty_{roll['id']}": "5"}).status_code, 403)
        self.assertEqual(c.post(f"/staff/inventory/{mal['id']}/item/{roll['id']}", data={"action": "receive", "qty": "5"}).status_code, 403)
        self.assertEqual(c.get("/staff/inventory/items").status_code, 403)
        self.assertNotIn("Update stock", c.get(f"/staff/inventory/{mal['id']}", query_string={"category": "Routine Disposables"}).data.decode())
        self.assertEqual(self.stock(mal["id"], roll["id"]), before)

    def test_role_granted_update_is_limited_to_own_locations(self):
        self.conn.execute("INSERT INTO role_permissions (role, permission) VALUES ('staff', 'inventory.manage')")
        try:
            c = self.login("staff.bocaue")
            boc, mal = self.loc("Bocaue%"), self.loc("Malolos%")
            gauze = self.item("Cotton Gauze")
            r = c.post(f"/staff/inventory/{boc['id']}/item/{gauze['id']}", data={"action": "receive", "qty": "10", "expiry": "2030-01-31"})
            self.assertEqual(r.status_code, 302)
            s = self.stock(boc["id"], gauze["id"])
            self.assertEqual((s["qty"], s["expiry_date"]), (10, "2030-01-31"))
            self.assertEqual(c.post(f"/staff/inventory/{mal['id']}/item/{gauze['id']}", data={"action": "receive", "qty": "3"}).status_code, 404)
        finally:
            self.conn.execute("DELETE FROM role_permissions WHERE role = 'staff' AND permission = 'inventory.manage'")

    def test_bulk_count_statuses_and_history(self):
        from app.util import today
        c = self.login("admin")
        loc = self.loc("Guiguinto%")
        cat = "Anesthetics & Pharmaceuticals"
        lido, arti, mepi, needle = (self.item(n) for n in ("Anesthesia (Lidocaine)", "Anesthesia (Articaine)", "Anesthesia (Mepivacaine)", "Needle Long"))
        page = c.get(f"/staff/inventory/{loc['id']}", query_string={"category": cat, "edit": "1"}).data.decode()
        self.assertIn(f'name="qty_{lido["id"]}"', page)
        soon = (today() + timedelta(days=30)).isoformat()
        past = (today() - timedelta(days=2)).isoformat()
        r = c.post(f"/staff/inventory/{loc['id']}", data={
            "category": cat,
            f"qty_{lido['id']}": "4", f"reorder_{lido['id']}": "2", f"expiry_{lido['id']}": soon,
            f"qty_{arti['id']}": "2", f"reorder_{arti['id']}": "2", f"expiry_{arti['id']}": "",
            f"qty_{mepi['id']}": "1", f"reorder_{mepi['id']}": "", f"expiry_{mepi['id']}": past,
            f"qty_{needle['id']}": "0", f"reorder_{needle['id']}": "1", f"expiry_{needle['id']}": ""})
        self.assertEqual(r.status_code, 302)
        from app.views.inventory import status_of
        st = {i["name"]: status_of(dict(self.stock(loc["id"], i["id"]))) for i in (lido, arti, mepi, needle)}
        self.assertEqual(st, {"Anesthesia (Lidocaine)": "expiring", "Anesthesia (Articaine)": "reorder",
                              "Anesthesia (Mepivacaine)": "expired", "Needle Long": "out"})
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM inventory_moves WHERE location_id = ? AND kind = 'count'", (loc["id"],)), 4)
        # Bad input: nothing saved, row flagged
        r = c.post(f"/staff/inventory/{loc['id']}", data={"category": cat, f"qty_{lido['id']}": "-3"})
        self.assertIn("need fixing", r.data.decode())
        self.assertEqual(self.stock(loc["id"], lido["id"])["qty"], 4)
        # Receive, use, over-use refused
        base = f"/staff/inventory/{loc['id']}/item/{arti['id']}"
        c.post(base, data={"action": "receive", "qty": "5", "expiry": "2031-06-30", "note": "DR 1234"})
        self.assertEqual(self.stock(loc["id"], arti["id"])["qty"], 7)
        c.post(base, data={"action": "remove", "qty": "3", "reason": "used"})
        self.assertEqual(self.stock(loc["id"], arti["id"])["qty"], 4)
        r = c.post(base, data={"action": "remove", "qty": "50", "reason": "used"})
        self.assertIn("Only 4", r.data.decode())
        hist = c.get(base).data.decode()
        for part in ("Received", "Used in clinic", "DR 1234", "Demo Super Admin"):
            self.assertIn(part, hist)
        self.assertTrue(self.q("SELECT id FROM audit_log WHERE action = 'inventory_received'"))
        # Overview lists what needs attention
        ov = c.get("/staff/inventory").data.decode()
        self.assertIn("Needs attention", ov)
        self.assertIn("Anesthesia (Mepivacaine)", ov)

    def test_new_item_needs_a_count_before_reorder(self):
        c = self.login("admin")
        loc = self.loc("San Jose%")
        bib = self.item("Bib")
        r = c.post(f"/staff/inventory/{loc['id']}", data={"category": "Routine Disposables", f"qty_{bib['id']}": "", f"reorder_{bib['id']}": "3"})
        self.assertIn("Enter the quantity on hand too", r.data.decode())
        self.assertIsNone(self.stock(loc["id"], bib["id"]))

    def test_lab_member_sees_lab_location(self):
        from app.auth import hash_password
        from app.util import now_str
        lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")
        uid = self.conn.insert("users", {"email": "lab.tech@demo.dentalhaven.test", "name": "Lab Tech (demo)", "password_hash": hash_password("DemoPass-2026x"),
                                         "role": "staff", "active": 1, "must_change_password": 0, "created_at": now_str()})
        self.conn.execute("INSERT INTO user_labs (user_id, lab_id) VALUES (?, ?)", (uid, lab["id"]))
        c = self.app.test_client()
        c.post("/staff/login", data={"email": "lab.tech@demo.dentalhaven.test", "password": "DemoPass-2026x"})
        r = c.get("/staff/inventory")
        self.assertEqual(r.status_code, 302)  # only one location: goes straight to it
        self.assertIn("Digital Solutions Dental Laboratory", c.get(r.headers["Location"]).data.decode())

    def test_items_prices_and_export(self):
        c = self.login("admin")
        roll = self.item("Cotton Roll")
        r = c.post(f"/staff/inventory/items/{roll['id']}", data={"name": "Cotton Roll", "unit": "pack", "category": "Routine Disposables",
                                                                 "price": "185.50", "supplier": "=HYPERLINK(1)", "active": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.item("Cotton Roll")["unit_price_cents"], 18550)
        r = c.post("/staff/inventory/items", data={"name": "Cotton Roll", "unit": "pack", "category": "Routine Disposables"})
        self.assertIn("already exists", r.data.decode())
        r = c.post("/staff/inventory/items", data={"name": "Saliva Ejector", "unit": "pack", "category": "Routine Disposables", "price": "120"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.item("Saliva Ejector")["code"].startswith("DH-0593"))
        loc = self.loc("Malolos%")
        c.post(f"/staff/inventory/{loc['id']}/item/{roll['id']}", data={"action": "settings", "qty": "4", "reorder": "2", "expiry": ""})
        csv_text = c.get(f"/staff/inventory/{loc['id']}/export.csv").data.decode("utf-8-sig")
        self.assertIn("Code,Group,Category,Item", csv_text)
        line = next(l for l in csv_text.splitlines() if ",Cotton Roll," in l)
        self.assertIn(",4,2,,185.5,742.0,OK,'=HYPERLINK(1)", line)
