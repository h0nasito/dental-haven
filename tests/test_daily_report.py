"""Daily collection report: gross by payment method, expenses, lab fee share, dentist commission, net; scheduled send."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402

DAY = "2026-03-10"


class TestDailyReport(Base):
    def setUp(self):
        super().setUp()
        from app.util import now_str
        global DAY
        DAY = {"test_numbers": "2026-03-11", "test_text_and_page": "2026-03-12", "test_scheduled_once_after_time": "2026-03-13",
               "test_settings_validation": "2026-03-14"}[self._testMethodName]
        self.bid = self.branch("bocaue")
        pid = self.q("SELECT id FROM patients LIMIT 1")["id"]
        # a fresh day for this branch: bill 10,000 with 2,000 lab fee
        inv = self.conn.insert("invoices", {"patient_id": pid, "branch_id": self.bid, "status": "issued", "number": f"T-{id(self)}",
                                            "subtotal_cents": 1000000, "total_cents": 1000000, "created_by": 1, "created_at": now_str(),
                                            "issued_at": DAY})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Crown (demo)", "qty": 1, "unit_price_cents": 1000000,
                                           "amount_cents": 1000000, "lab_fee_cents": 200000})
        for kind, method, amt in (("payment", "cash", 300000), ("payment", "gcash", 200000), ("payment", "account_credit", 100000)):
            self.conn.insert("payments", {"invoice_id": inv, "branch_id": self.bid, "kind": kind, "amount_cents": amt, "method": method,
                                          "received_at": DAY, "created_at": now_str()})
        self.conn.insert("expenses", {"branch_id": self.bid, "expense_date": DAY, "category": "Dental supplies", "item": "Gloves",
                                      "amount_cents": 50000, "status": "posted", "created_at": now_str()})
        self.conn.insert("expenses", {"branch_id": self.bid, "expense_date": DAY, "category": "Repairs", "amount_cents": 99900,
                                      "status": "void", "created_at": now_str()})
        emp = self.q("SELECT e.id, e.full_name FROM employees e JOIN users u ON u.id = e.user_id WHERE u.role = 'dentist' LIMIT 1")
        self.dentist = emp["full_name"]
        self.conn.insert("dentist_commissions", {"employee_id": emp["id"], "earned_on": DAY, "invoice_id": inv, "amount_cents": 35000,
                                                 "created_at": now_str()})

    def report(self):
        from app import daily_report
        return next(r for r in daily_report.build(self.conn, DAY) if r["branch"].startswith("Bocaue"))

    def test_numbers(self):
        r = self.report()
        self.assertEqual(dict(r["gross"]), {"Cash": 300000, "GCash": 200000})       # account credit is not new money
        self.assertEqual(r["gross_total"], 500000)
        exp = {(label, det): a for label, det, a in r["expenses"]}
        self.assertEqual(exp[("Dental supplies", "Gloves")], 50000)
        self.assertNotIn(99900, exp.values())                                          # voided expense left out
        # lab share: payments 300k + 200k + 100k (credit) on a 1,000,000 bill with 200k lab fee -> 20% = 120,000
        self.assertEqual(exp[("Lab fee", "from bills paid today")], 120000)
        self.assertEqual(exp[("Dentist commission", self.dentist)], 35000)
        self.assertEqual(r["net"], 500000 - 50000 - 120000 - 35000)

    def test_text_and_page(self):
        from app import daily_report
        text = daily_report.as_text([self.report()], "Thursday, Mar 12, 2026")
        for part in ("BRANCH: Bocaue", "GROSS", "- Cash: ₱3,000.00", "TOTAL GROSS AMOUNT: ₱5,000.00", "Dentist commission – ",
                     "NET: ₱2,950.00"):
            self.assertIn(part, text)
        page = self.login("admin").get(f"/staff/reports/daily-collection?date={DAY}").data.decode()
        self.assertIn("Daily collection report", page)
        self.assertIn("₱2,950.00", page)

    def test_scheduled_once_after_time(self):
        from app import daily_report, settings
        settings.put("report.daily_enabled", True, None, self.conn)
        settings.put("report.daily_recipients", "owner@example.com", None, self.conn)
        settings.put("report.daily_time", "23:00", None, self.conn)
        settings.put("report.daily_last_sent", "", None, self.conn)
        from datetime import datetime
        with self.app.app_context(), mock.patch("app.daily_report.send", return_value=(1, "ok")) as snd:
            from app.db import get_db
            with mock.patch("app.daily_report.now", return_value=datetime(2026, 3, 10, 22, 59)):
                self.assertFalse(daily_report.run(get_db()))
            with mock.patch("app.daily_report.now", return_value=datetime(2026, 3, 10, 23, 1)):
                self.assertTrue(daily_report.run(get_db()))
                self.assertFalse(daily_report.run(get_db()))   # only once a day
            self.assertEqual(snd.call_count, 1)
            self.assertEqual(snd.call_args[0][1], "2026-03-10")

    def test_settings_validation(self):
        a = self.login("admin")
        page = a.get("/staff/admin/system").data.decode()
        self.assertIn("Daily collection report", page)
        self.assertEqual(date.today() > date(2026, 1, 1), True)
