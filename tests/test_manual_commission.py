"""Manual dentist commission: per bill line (manual % or fixed amount) and manual entries (bill, payment, payroll page)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402
from test_patient_profile import PNG  # noqa: E402


class TestManualCommission(Base):
    def test_ortho_package_paid_in_parts(self):
        from app.util import now_str
        conn = self.conn
        from app import settings
        settings.put("payroll.dentist_commission_basis", "procedure", None, conn)
        self.addCleanup(settings.put, "payroll.dentist_commission_basis", "payment", None, conn)
        doc = self.q("SELECT id FROM users WHERE email = 'dentist.sjdm@demo.dentalhaven.test'")["id"]
        emp = self.q("SELECT * FROM employees WHERE user_id = ?", (doc,))
        sjdm = self.branch("sjdm")
        admin = self.login("admin")
        admin.post(f"/staff/employees/{emp['id']}", data={"action": "dentist_pay", "daily_rate": "1500", "commission": "40",
                                                            "effective_from": "2020-01-01"})
        patient = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (doc,))["id"]
        day = "2025-04-03"
        inv = conn.insert("invoices", {"number": "TEST-MC-1", "branch_id": sjdm, "patient_id": patient, "status": "issued", "issued_at": day,
                                       "subtotal_cents": 5000000, "total_cents": 5000000, "created_at": now_str()})
        ortho = conn.insert("invoice_items", {"invoice_id": inv, "description": "Orthodontic treatment (metal braces)", "qty": 1,
                                              "unit_price_cents": 4600000, "amount_cents": 4600000, "dentist_id": doc, "done_on": day})
        crown = conn.insert("invoice_items", {"invoice_id": inv, "description": "PFM crown", "qty": 1, "unit_price_cents": 400000,
                                              "amount_cents": 400000, "dentist_id": doc, "done_on": day})
        # ortho package line: manual amount 0; crown: manual 50%
        admin.post(f"/staff/invoices/{inv}/edit", data={"action": "commission", "item_id": ortho, "dentist_id": doc, "done_on": day,
                                                         "commission_mode": "amount", "commission_amount": "0"})
        admin.post(f"/staff/invoices/{inv}/edit", data={"action": "commission", "item_id": crown, "dentist_id": doc, "done_on": day,
                                                         "commission_mode": "percent", "commission_pct": "50"})
        self.assertEqual(tuple(self.q("SELECT commission_mode, commission_cents FROM invoice_items WHERE id = ?", (ortho,)).values()), ("amount", 0))
        self.assertEqual(tuple(self.q("SELECT commission_mode, commission_bp FROM invoice_items WHERE id = ?", (crown,)).values()), ("percent", 5000))
        # bad % is refused and nothing changes
        admin.post(f"/staff/invoices/{inv}/edit", data={"action": "commission", "item_id": crown, "dentist_id": doc, "done_on": day,
                                                         "commission_mode": "percent", "commission_pct": "150"})
        self.assertEqual(self.q("SELECT commission_bp FROM invoice_items WHERE id = ?", (crown,))["commission_bp"], 5000)
        # adjustment #1: patient pays 1,500 -> 40% recorded from the bill page
        admin.post(f"/staff/invoices/{inv}/dentist-commission", data={"dentist_id": doc, "earned_on": "2025-04-05", "base": "1500",
                                                                       "pct": "40", "description": "Braces adjustment"})
        # adjustment #2: recorded together with the payment (40% of 1,000)
        admin.post(f"/staff/invoices/{inv}/payments", data={"action": "multi", "method": ["cash"], "amount": ["1000"], "received_at": "2025-04-10",
                                                            "signature": "data:image/png;base64," + PNG, "comm_dentist_id": doc,
                                                            "comm_pct": "40", "comm_desc": "Braces adjustment"})
        rows = conn.all("SELECT * FROM dentist_commissions WHERE invoice_id = ? ORDER BY id", (inv,))
        self.assertEqual([(r["earned_on"], r["base_cents"], r["rate_bp"], r["amount_cents"]) for r in rows],
                         [("2025-04-05", 150000, 4000, 60000), ("2025-04-10", 100000, 4000, 40000)])
        self.assertIsNotNone(rows[1]["payment_id"])
        # payroll 1-15 April: crown 4,000 x 50% = 2,000 + ortho 0 + 600 + 400 = 3,000
        r = admin.post("/staff/payroll", data={"start_date": "2025-04-01", "end_date": "2025-04-15", "branch_id": "", "name": "Test Apr"})
        pid = int(r.headers["Location"].rsplit("/", 1)[1])
        # manual amount from the payroll page (inside the period), then recalculate
        admin.post(f"/staff/payroll/{pid}/dentist/{emp['id']}/manual", data={"earned_on": "2025-04-12", "description": "Agreed amount",
                                                                             "amount": "250"})
        admin.post(f"/staff/payroll/{pid}", data={"action": "rebuild"})
        line = self.q("SELECT * FROM payroll_lines WHERE period_id = ? AND employee_id = ?", (pid, emp["id"]))
        self.assertEqual(line["commission_cents"], 200000 + 60000 + 40000 + 25000)
        page = admin.get(f"/staff/payroll/{pid}/dentist/{emp['id']}").data.decode()
        for part in ("Manual commission", "Braces adjustment", "Agreed amount", "₱3,250.00", "fixed", "50.0%"):
            self.assertIn(part, page)
        # outside the period: refused
        admin.post(f"/staff/payroll/{pid}/dentist/{emp['id']}/manual", data={"earned_on": "2025-04-20", "description": "x", "amount": "1"})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM dentist_commissions WHERE employee_id = ? AND earned_on BETWEEN '2025-04-01' AND '2025-04-30'", (emp["id"],))["n"], 3)
        # remove one from the bill page
        admin.post(f"/staff/invoices/{inv}/dentist-commission", data={"action": "void", "commission_id": rows[0]["id"]})
        self.assertEqual(self.q("SELECT status FROM dentist_commissions WHERE id = ?", (rows[0]["id"],))["status"], "void")
        # front desk without bills.edit can't add commission
        front = self.login("staff.malolos")
        self.assertIn(front.post(f"/staff/invoices/{inv}/dentist-commission", data={"dentist_id": doc, "amount": "1"}).status_code, (403,))

    def test_commission_on_a_payment_row(self):
        from app.util import now_str
        conn = self.conn
        doc = self.q("SELECT id FROM users WHERE email = 'dentist.sjdm@demo.dentalhaven.test'")["id"]
        emp = self.q("SELECT * FROM employees WHERE user_id = ?", (doc,))
        patient = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (doc,))["id"]
        inv = conn.insert("invoices", {"number": "TEST-MC-2", "branch_id": self.branch("sjdm"), "patient_id": patient, "status": "issued",
                                       "issued_at": "2025-05-01", "subtotal_cents": 5000000, "total_cents": 5000000, "created_at": now_str()})
        admin = self.login("admin")
        admin.post(f"/staff/invoices/{inv}/payments", data={"action": "multi", "method": ["cash"], "amount": ["1500"], "received_at": "2025-05-20",
                                                            "notes": "adjustment", "not_signed_reason": "test"})
        pay = self.q("SELECT id FROM payments WHERE invoice_id = ?", (inv,))["id"]
        page = admin.get(f"/staff/invoices/{inv}").data.decode()
        self.assertIn("Dentist commission", page)
        self.assertIn(f'name="payment_id" value="{pay}"', page)
        admin.post(f"/staff/invoices/{inv}/dentist-commission", data={"payment_id": pay, "dentist_id": doc, "pct": "40"})
        c = self.q("SELECT * FROM dentist_commissions WHERE payment_id = ?", (pay,))
        self.assertEqual((c["earned_on"], c["base_cents"], c["rate_bp"], c["amount_cents"], c["description"], c["employee_id"]),
                         ("2025-05-20", 150000, 4000, 60000, "adjustment", emp["id"]))
        # only one per payment
        admin.post(f"/staff/invoices/{inv}/dentist-commission", data={"payment_id": pay, "dentist_id": doc, "amount": "100"})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM dentist_commissions WHERE payment_id = ?", (pay,))["n"], 1)
        self.assertIn("₱600.00", admin.get(f"/staff/invoices/{inv}").data.decode())
        # voiding the payment removes its commission
        admin.post(f"/staff/invoices/{inv}/payments", data={"action": "void_payment", "payment_id": pay, "reason": "wrong amount"})
        self.assertEqual(self.q("SELECT status FROM dentist_commissions WHERE id = ?", (c["id"],))["status"], "void")

    def test_cashier_commission_per_payment(self):
        """Default: the cashier records commission on each payment; bill lines aren't counted (no double pay)."""
        from app.util import now_str
        conn = self.conn
        doc = self.q("SELECT id FROM users WHERE email = 'dentist.sjdm@demo.dentalhaven.test'")["id"]
        emp = self.q("SELECT * FROM employees WHERE user_id = ?", (doc,))
        admin = self.login("admin")
        admin.post(f"/staff/employees/{emp['id']}", data={"action": "dentist_pay", "daily_rate": "1500", "commission": "40",
                                                            "effective_from": "2020-01-01"})
        patient = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (doc,))["id"]
        sjdm = self.branch("sjdm")
        # crown 20,000 with a 5,000 lab fee (25% of the bill)
        inv = conn.insert("invoices", {"number": "TEST-CC-1", "branch_id": sjdm, "patient_id": patient, "status": "issued",
                                       "issued_at": "2025-06-02", "subtotal_cents": 2000000, "total_cents": 2000000, "created_at": now_str()})
        conn.insert("invoice_items", {"invoice_id": inv, "description": "Zirconia crown", "qty": 1, "unit_price_cents": 2000000,
                                      "amount_cents": 2000000, "dentist_id": doc, "done_on": "2025-06-02", "lab_fee_cents": 500000})
        # cashiers get the "Record dentist commission" permission by default
        self.assertIsNotNone(self.q("SELECT 1 AS x FROM role_permissions WHERE role = 'cashier' AND permission = 'commission.record'"))
        # the payment form is pre-filled with the bill's dentist and their usual %
        page = admin.get(f"/staff/invoices/{inv}").data.decode()
        self.assertIn("data-comm ", page)
        self.assertIn(f'<option value="{doc}" data-rate="40.0" selected>', page)
        # payment 10,000 at 40%: lab share 2,500 -> base 7,500 -> 3,000
        admin.post(f"/staff/invoices/{inv}/payments", data={"action": "multi", "method": ["cash"], "amount": ["10000"], "received_at": "2025-06-03",
                                                            "not_signed_reason": "test", "comm_dentist_id": doc, "comm_mode": "percent", "comm_pct": "40"})
        # second payment with a manual amount
        admin.post(f"/staff/invoices/{inv}/payments", data={"action": "multi", "method": ["gcash"], "amount": ["10000"], "received_at": "2025-06-10",
                                                            "not_signed_reason": "test", "comm_dentist_id": doc, "comm_mode": "amount", "comm_amount": "2500"})
        rows = conn.all("SELECT * FROM dentist_commissions WHERE invoice_id = ? ORDER BY id", (inv,))
        self.assertEqual([(r["earned_on"], r["base_cents"], r["rate_bp"], r["amount_cents"]) for r in rows],
                         [("2025-06-03", 750000, 4000, 300000), ("2025-06-10", 750000, None, 250000)])
        # a bad % is refused and no payment is saved
        admin.post(f"/staff/invoices/{inv}/payments", data={"action": "multi", "method": ["cash"], "amount": ["100"], "not_signed_reason": "t",
                                                            "comm_dentist_id": doc, "comm_mode": "percent", "comm_pct": "140"})
        n = self.q("SELECT COUNT(*) AS n FROM payments WHERE invoice_id = ?", (inv,))["n"]
        # payroll 1-15 June: only payment commissions (5,500); the crown line itself is not counted
        r = admin.post("/staff/payroll", data={"start_date": "2025-06-01", "end_date": "2025-06-15", "branch_id": "", "name": "Test Jun"})
        pid = int(r.headers["Location"].rsplit("/", 1)[1])
        line = self.q("SELECT * FROM payroll_lines WHERE period_id = ? AND employee_id = ?", (pid, emp["id"]))
        self.assertEqual(line["commission_cents"], 550000)
        self.assertIn("per payment", admin.get(f"/staff/payroll/{pid}/dentist/{emp['id']}").data.decode())
        self.assertEqual(n, 2)
