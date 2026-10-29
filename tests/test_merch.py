"""Merchandise: products, stock per branch, sales with their own receipts and payments (synthetic data only)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestMerch(Base):
    def setUp(self):
        self.b = self.branch("malolos")
        self.paste = self.q("SELECT id FROM merch_products WHERE name = 'Toothpaste - sensitive teeth'")["id"]
        self.amox = self.q("SELECT id, rx_required FROM merch_products WHERE name = 'Amoxicillin 500 mg capsule'")

    def stock(self, pid):
        return self.conn.scalar("SELECT qty FROM merch_stock WHERE product_id = ? AND branch_id = ?", (pid, self.b)) or 0

    def test_products_stock_sale_void(self):
        self.assertEqual(self.amox["rx_required"], 1)
        a = self.login("admin")
        self.assertEqual(a.get("/staff/merch/products").status_code, 200)
        a.post("/staff/merch/products", data={"product_id": self.paste, "name": "Toothpaste - sensitive teeth", "category": "Oral care",
                                              "unit": "tube", "price": "250", "cost": "180", "reorder_level": "3", "active": "1"})
        self.assertEqual(self.q("SELECT price_cents FROM merch_products WHERE id = ?", (self.paste,))["price_cents"], 25000)
        before = self.stock(self.paste)
        a.post("/staff/merch/stock", data={"branch_id": self.b, "action": "in", "product_id": self.paste, "qty": "10", "unit_cost": "175",
                                           "expiry_date": "2027-06-30"})
        self.assertEqual(self.stock(self.paste), before + 10)
        # staff sells 2 (paid in full by default); can't sell more than in stock
        s = self.login("staff.malolos")
        self.assertIn("in stock", s.post("/staff/merch/new", data={"branch_id": self.b, "product_0": self.paste, "qty_0": "999",
                                                                   "pay_method": "cash"}).data.decode())
        r = s.post("/staff/merch/new", data={"branch_id": self.b, "buyer_name": "Walk-in Buyer", "product_0": self.paste, "qty_0": "2",
                                             "pay_method": "cash"})
        self.assertEqual(r.status_code, 302, r.data[:500])
        sale = self.q("SELECT * FROM merch_sales ORDER BY id DESC LIMIT 1")
        self.assertTrue(sale["number"].startswith("MS-"))
        self.assertEqual(sale["total_cents"], 50000)
        self.assertEqual(self.conn.scalar("SELECT SUM(amount_cents) FROM merch_payments WHERE sale_id = ?", (sale["id"],)), 50000)
        self.assertEqual(self.stock(self.paste), before + 8)
        self.assertIn(sale["number"], s.get(f"/staff/merch/{sale['id']}/receipt").data.decode())
        self.assertIn("Walk-in Buyer", s.get("/staff/merch/").data.decode())
        self.assertIn("Toothpaste - sensitive teeth", a.get("/staff/merch/report?from=2000-01-01").data.decode())
        # not a patient bill
        self.assertFalse(self.q("SELECT id FROM invoices WHERE notes LIKE '%MS-%'"))
        # other branches can't open it; staff can't void
        self.assertEqual(self.login("reception.bocaue").get(f"/staff/merch/{sale['id']}").status_code, 404)
        self.assertEqual(s.post(f"/staff/merch/{sale['id']}/void", data={"reason": "x"}).status_code, 403)
        # admin voids payment then sale: stock goes back
        p = self.q("SELECT id FROM merch_payments WHERE sale_id = ?", (sale["id"],))
        a.post(f"/staff/merch/{sale['id']}/payments/{p['id']}/void", data={"reason": "returned"})
        a.post(f"/staff/merch/{sale['id']}/void", data={"reason": "returned"})
        self.assertEqual(self.q("SELECT status FROM merch_sales WHERE id = ?", (sale["id"],))["status"], "void")
        self.assertEqual(self.stock(self.paste), before + 10)
        # count correction
        a.post("/staff/merch/stock", data={"branch_id": self.b, "action": "count", "product_id": self.paste, "counted": "4", "notes": "monthly count"})
        self.assertEqual(self.stock(self.paste), 4)
        # pages
        for url in ("/staff/merch/stock", "/staff/merch/report", "/staff/merch/new"):
            self.assertEqual(a.get(url).status_code, 200, url)

    def test_price_needed_and_access(self):
        a = self.login("admin")
        a.post("/staff/merch/stock", data={"branch_id": self.b, "action": "in", "product_id": self.amox["id"], "qty": "20"})
        r = a.post("/staff/merch/new", data={"branch_id": self.b, "product_0": self.amox["id"], "qty_0": "1", "pay_method": "cash"})
        self.assertIn("enter the price", r.data.decode())
        d = self.login("dentist.malolos")
        self.assertEqual(d.get("/staff/merch/").status_code, 403)
        s = self.login("staff.malolos")
        self.assertEqual(s.get("/staff/merch/products").status_code, 403)
        self.assertEqual(s.post("/staff/merch/stock", data={"branch_id": self.b, "action": "in", "product_id": self.amox["id"], "qty": "1"}).status_code, 403)
