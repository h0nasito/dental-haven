"""Lab price list: DSDL prices loaded, lab billing users edit, branch staff view, pickers on the invoice."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_lab_case_billing import TestLabCaseBilling  # noqa: E402


class TestLabPrices(TestLabCaseBilling):
    test_lab_sets_price_and_bills_branch = None
    test_bill_by_case_with_units_extras_and_less = None

    def test_dsdl_prices_loaded(self):
        n = self.q("SELECT COUNT(*) AS n FROM lab_price_items WHERE lab_id = ?", (self.lab,))["n"]
        self.assertEqual(n, 48)
        z = self.q("SELECT price_cents FROM lab_price_items WHERE lab_id = ? AND name = 'Zirconia premium'", (self.lab,))
        self.assertEqual(z["price_cents"], 550000)

    def test_lab_billing_edits_and_branch_views(self):
        page = self.t.get("/staff/lab/prices").data.decode()
        self.assertIn("Save price list", page)
        it = self.q("SELECT * FROM lab_price_items WHERE lab_id = ? AND name = 'Zirconia premium'", (self.lab,))
        r = self.t.post("/staff/lab/prices", data={"action": "save", f"name_{it['id']}": it["name"], f"price_{it['id']}": "5800",
                                                    f"unit_{it['id']}": "unit", f"note_{it['id']}": "", f"active_{it['id']}": "1"})
        self.assertIn(r.status_code, (200, 302))
        self.assertEqual(self.q("SELECT price_cents FROM lab_price_items WHERE id = ?", (it["id"],))["price_cents"], 580000)
        self.t.post("/staff/lab/prices", data={"action": "add", "lab_id": self.lab, "category": "Others", "name": "Test item X", "price": "123"})
        self.assertIsNotNone(self.q("SELECT id FROM lab_price_items WHERE name = 'Test item X'"))
        d = self.login("dentist.malolos")
        page = d.get("/staff/lab/prices").data.decode()
        self.assertIn("Zirconia premium", page)
        self.assertNotIn("Save price list", page)
        self.assertEqual(d.post("/staff/lab/prices", data={"action": "add", "lab_id": self.lab, "name": "Nope", "price": "1"}).status_code, 403)

    def test_picker_on_invoice(self):
        r = self.t.post(f"/staff/lab/cases/{self.case}/bill")
        page = self.t.get(r.headers["Location"]).data.decode()
        self.assertIn("data-price-pick", page)
        self.assertIn('data-price="5500.00"', page)


del TestLabCaseBilling
