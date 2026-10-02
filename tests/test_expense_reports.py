"""Expenses: detailed daily entries (time, item, qty x unit price, spent by, receipt) and daily / monthly / by-date reports per branch."""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n" + b"0" * 200)


class TestExpenseReports(Base):
    def _add(self, c, branch, day, item, qty, unit, cat="Dental supplies", **extra):
        data = {"branch_id": branch, "expense_date": day, "expense_time": "10:15", "category": cat, "item": item, "qty": qty,
                "unit_price": unit, "method": "cash", **extra}
        return c.post("/staff/expenses/", data=data, content_type="multipart/form-data")

    def test_entry_and_reports(self):
        admin = self.login("admin")
        mal, boc = self.branch("malolos"), self.branch("bocaue")
        self._add(admin, mal, "2025-03-03", "TEST Gloves (box)", "3", "250", spent_by="Test Person", payee="Supplier A", reference="OR-1",
                  receipt=(io.BytesIO(PNG), "or.png"))
        self._add(admin, mal, "2025-03-03", "TEST Meralco bill", "1", "4500", cat="Utilities (power, water, internet)")
        self._add(admin, boc, "2025-03-15", "TEST Lunch", "1", "", amount="600", cat="Food & meals")
        self._add(admin, boc, "2025-04-01", "TEST April item", "1", "100")
        rows = {r["item"]: r for r in self.conn.all("SELECT * FROM expenses WHERE item LIKE 'TEST %'")}
        g = rows["TEST Gloves (box)"]
        self.assertEqual((g["amount_cents"], g["qty"], g["unit_price_cents"], g["expense_time"], g["spent_by"], g["payee"]),
                         (75000, 3.0, 25000, "10:15", "Test Person", "Supplier A"))
        self.assertTrue(g["receipt_stored"])
        self.assertEqual(rows["TEST Lunch"]["amount_cents"], 60000)
        self.assertEqual(admin.get(f"/staff/expenses/{g['id']}/receipt").status_code, 200)
        # post all but the April one
        for name in ("TEST Gloves (box)", "TEST Meralco bill", "TEST Lunch"):
            admin.post(f"/staff/expenses/{rows[name]['id']}/post")
        # daily report: Malolos only items on Mar 3
        daily = admin.get(f"/staff/expenses/report?mode=daily&day=2025-03-03&branch={mal}").data.decode()
        self.assertIn("₱5,250.00", daily)
        self.assertNotIn("TEST Lunch", daily)
        # monthly March, both branches: per-branch totals and grand total
        monthly = admin.get(f"/staff/expenses/report?mode=monthly&month=2025-03&branch={mal}&branch={boc}").data.decode()
        self.assertIn("March 2025", monthly)
        self.assertIn("₱5,250.00", monthly)
        self.assertIn("₱600.00", monthly)
        self.assertIn("₱5,850.00", monthly)
        self.assertNotIn("TEST April item", monthly)
        # category filter: only utilities
        util = admin.get(f"/staff/expenses/report?mode=monthly&month=2025-03&branch={mal}&branch={boc}"
                         "&category=Utilities+%28power%2C+water%2C+internet%29").data.decode()
        self.assertIn("TEST Meralco bill", util)
        self.assertNotIn("TEST Gloves (box)", util)
        self.assertNotIn("TEST Lunch", util)
        self.assertIn("₱4,500.00", util)
        # by date, with drafts included
        rng = admin.get(f"/staff/expenses/report?mode=range&from=2025-03-01&to=2025-04-30&branch={boc}&pending=1").data.decode()
        self.assertIn("TEST April item", rng)
        self.assertIn("₱700.00", rng)
        csv_text = admin.get(f"/staff/expenses/report?mode=monthly&month=2025-03&branch={mal}&branch={boc}&format=csv").data.decode("utf-8-sig")
        self.assertIn("ALL BRANCHES,3,5850.0", csv_text)
        self.assertIn("TEST Gloves (box)", csv_text)
        # validation: no price
        r = self._add(admin, mal, "2025-03-04", "TEST No price", "1", "")
        self.assertIsNone(self.q("SELECT id FROM expenses WHERE item = 'TEST No price'"))
        # a dentist without expense access can't see reports
        self.assertEqual(self.login("dentist.sjdm").get("/staff/expenses/report").status_code, 403)
        self.conn.execute("DELETE FROM expenses WHERE item LIKE 'TEST %'")
