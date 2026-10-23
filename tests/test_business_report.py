"""Monthly business report: scorecard, ratios, groups and takeaways from recorded data."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestBusinessReport(Base):
    def test_report_numbers(self):
        from datetime import date
        from app import business_report as br
        from app.util import now_str
        bid = self.branch("bocaue")
        # a quiet past month for this branch: one bill paid, some expenses
        m = date(2025, 3, 1)
        pid = self.q("SELECT id FROM patients LIMIT 1")["id"]
        inv = self.conn.insert("invoices", {"branch_id": bid, "patient_id": pid, "status": "issued", "issued_at": "2025-03-05 10:00:00", "number": "BR-QT-1",
                                            "subtotal_cents": 10000000, "total_cents": 10000000, "created_at": now_str()})
        self.conn.insert("payments", {"invoice_id": inv, "branch_id": bid, "kind": "payment", "amount_cents": 10000000, "method": "cash",
                                      "received_at": "2025-03-05 10:00:00", "status": "valid", "created_at": now_str()})
        for cat, amt in (("Dental supplies", 800000), ("Rent", 2000000), ("Marketing & advertising", 500000), ("Salaries & wages", 3000000)):
            self.conn.insert("expenses", {"branch_id": bid, "category": cat, "item": cat, "qty": 1, "amount_cents": amt, "expense_date": "2025-03-10",
                                          "method": "cash", "status": "posted", "created_at": now_str()})
        with self.app.app_context():
            from app.db import get_db
            conn = get_db()
            branches = conn.all("SELECT * FROM branches WHERE id = ?", (bid,))
            f = br.figures(conn, branches, *br.month_bounds(m))
        self.assertEqual((f["gross"], f["expenses"], f["payroll"], f["net"]), (10000000, 3300000, 3000000, 3700000))
        self.assertEqual((f["margin"], f["supply_pct"], f["payroll_pct"]), (37.0, 8.0, 30.0))
        self.assertEqual(f["groups"]["Fixed overhead"]["total"], 2000000)
        c = self.login("admin")
        page = c.get(f"/staff/reports/business?month=2025-03&branch={bid}").data.decode()
        for t in ("1. Scorecard", "2. Key ratios", "3. Costs by group", "4. Key takeaways", "37.0%", "net profit"):
            self.assertIn(t, page)
        csv_ = c.get(f"/staff/reports/business?month=2025-03&branch={bid}&format=csv").data.decode("utf-8-sig")
        self.assertIn("Net profit margin %,37.0", csv_)
        self.assertEqual(c.get("/staff/reports/business").status_code, 200)

    def test_dentist_cannot_open(self):
        self.assertEqual(self.login("dentist.malolos").get("/staff/reports/business").status_code, 403)
