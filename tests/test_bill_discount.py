"""Discount on an issued bill: amount or %, with a reason; never below what's paid (synthetic data only)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestIssuedDiscount(Base):
    def make_bill(self):
        from app.util import now_str
        b = self.branch("malolos")
        pid = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (b,))["id"]
        inv = self.conn.insert("invoices", {"branch_id": b, "patient_id": pid, "status": "issued", "number": f"T-{now_str()[-8:]}",
                                            "issued_at": "2026-10-01", "subtotal_cents": 200000, "discount_cents": 0, "tax_cents": 0,
                                            "total_cents": 200000, "created_at": now_str()})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Extraction", "qty": 1, "unit_price_cents": 200000,
                                           "discount_cents": 0, "amount_cents": 200000})
        return inv

    def test_discount_amount_percent_and_limits(self):
        inv = self.make_bill()
        a = self.login("admin")
        self.assertIn("Apply discount", a.get(f"/staff/invoices/{inv}").data.decode())
        a.post(f"/staff/invoices/{inv}/discount", data={"kind": "percent", "value": "20", "reason": "Senior citizen, ID checked"})
        r = self.q("SELECT total_cents, discount_cents, notes FROM invoices WHERE id = ?", (inv,))
        self.assertEqual((r["discount_cents"], r["total_cents"]), (40000, 160000))
        self.assertIn("Senior citizen", r["notes"])
        # reason needed
        a.post(f"/staff/invoices/{inv}/discount", data={"kind": "amount", "value": "100", "reason": ""})
        self.assertEqual(self.q("SELECT discount_cents FROM invoices WHERE id = ?", (inv,))["discount_cents"], 40000)
        # can't go below what's paid
        from app.util import now_str
        self.conn.insert("payments", {"invoice_id": inv, "branch_id": self.branch("malolos"), "kind": "payment", "amount_cents": 150000,
                                      "method": "cash", "received_at": now_str(), "status": "valid", "created_at": now_str()})
        a.post(f"/staff/invoices/{inv}/discount", data={"kind": "amount", "value": "1000", "reason": "promo"})
        self.assertEqual(self.q("SELECT total_cents FROM invoices WHERE id = ?", (inv,))["total_cents"], 160000)
        a.post(f"/staff/invoices/{inv}/discount", data={"kind": "amount", "value": "500", "reason": "promo"})
        self.assertEqual(self.q("SELECT total_cents FROM invoices WHERE id = ?", (inv,))["total_cents"], 150000)
        # a dentist (no bills.edit) can't
        self.assertEqual(self.login("dentist.malolos").post(f"/staff/invoices/{inv}/discount",
                                                            data={"kind": "amount", "value": "1", "reason": "x x"}).status_code, 403)


class TestDentistWhoDidWorkIsAssigned(Base):
    def test_bill_line_dentist_assigns_patient(self):
        from app.util import now_str
        uid = self.q("SELECT id FROM users WHERE email LIKE 'dentist.malolos@%'")["id"]
        b = self.branch("malolos")
        pid = self.conn.insert("patients", {"first_name": "Work", "last_name": "Assigntest", "chart_no": "DH-AS1", "preferred_branch_id": b,
                                            "created_at": now_str(), "updated_at": now_str()})
        self.assertIsNone(self.q("SELECT 1 AS x FROM patient_assignments WHERE patient_id = ?", (pid,)))
        inv = self.conn.insert("invoices", {"branch_id": b, "patient_id": pid, "status": "issued", "number": "AS-1", "issued_at": "2026-10-31",
                                            "subtotal_cents": 120000, "discount_cents": 0, "tax_cents": 0, "total_cents": 120000, "created_at": now_str()})
        line = self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Restoration", "qty": 1, "unit_price_cents": 120000,
                                                  "discount_cents": 0, "amount_cents": 120000, "done_on": "2026-10-31"})
        self.assertIsNone(self.q("SELECT 1 AS x FROM patient_assignments WHERE patient_id = ?", (pid,)))
        self.conn.execute("UPDATE invoice_items SET dentist_id = ? WHERE id = ?", (uid, line))
        self.assertIsNotNone(self.q("SELECT 1 AS x FROM patient_assignments WHERE patient_id = ? AND dentist_id = ?", (pid, uid)))
        page = self.login("dentist.malolos").get("/staff/my-cases/?from=2026-10-01&to=2026-10-31").data.decode()
        self.assertIn("Assigntest", page)
        # staff (not dentists) on a line don't get assigned
        staff = self.q("SELECT id FROM users WHERE email LIKE 'staff.malolos@%'")["id"]
        self.conn.execute("UPDATE invoice_items SET dentist_id = ? WHERE id = ?", (staff, line))
        self.assertIsNone(self.q("SELECT 1 AS x FROM patient_assignments WHERE patient_id = ? AND dentist_id = ?", (pid, staff)))

    def test_my_cases_shows_commission(self):
        from app.util import now_str
        uid = self.q("SELECT id FROM users WHERE email LIKE 'dentist.malolos@%'")["id"]
        emp = self.q("SELECT id FROM employees WHERE user_id = ?", (uid,))
        eid = emp["id"] if emp else self.conn.insert("employees", {"full_name": "Demo Dentist", "position": "Dentist", "employment_type": "regular",
                                                                    "user_id": uid, "active": 1, "created_at": now_str()})
        b = self.branch("malolos")
        pid = self.conn.insert("patients", {"first_name": "Comm", "last_name": "Casetest", "chart_no": "DH-CM1", "preferred_branch_id": b,
                                            "created_at": now_str(), "updated_at": now_str()})
        inv = self.conn.insert("invoices", {"branch_id": b, "patient_id": pid, "status": "issued", "number": "CM-1", "issued_at": "2026-10-31",
                                            "subtotal_cents": 240000, "discount_cents": 0, "tax_cents": 0, "total_cents": 240000, "created_at": now_str()})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "RESTORATION/PASTA-ANTERIOR", "qty": 2, "unit_price_cents": 120000,
                                           "discount_cents": 0, "amount_cents": 240000, "dentist_id": uid, "done_on": "2026-10-31"})
        self.conn.insert("dentist_commissions", {"employee_id": eid, "earned_on": "2026-10-31", "invoice_id": inv, "amount_cents": 72000,
                                                 "status": "valid", "created_at": now_str()})
        page = self.login("dentist.malolos").get("/staff/my-cases/?from=2026-10-01&to=2026-10-31&q=casetest").data.decode()
        self.assertIn("commission ₱720.00", page)


class TestPaymentBranch(Base):
    def test_received_at_other_branch_and_move_bill(self):
        from app.util import now_str
        mal, gui = self.branch("malolos"), self.branch("guiguinto")
        pid = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (mal,))["id"]
        inv = self.conn.insert("invoices", {"branch_id": mal, "patient_id": pid, "status": "issued", "number": f"RB-{now_str()[-6:]}",
                                            "issued_at": "2026-10-17", "subtotal_cents": 500000, "discount_cents": 0, "tax_cents": 0,
                                            "total_cents": 500000, "created_at": now_str()})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Crown", "qty": 1, "unit_price_cents": 500000, "discount_cents": 0,
                                           "amount_cents": 500000})
        a = self.login("admin")
        page = a.get(f"/staff/invoices/{inv}").data.decode()
        self.assertIn("Received at (branch)", page)
        self.assertIn("Branch of this bill", page)
        # move the unpaid bill to Guiguinto and back
        a.post(f"/staff/invoices/{inv}/branch", data={"branch_id": gui})
        self.assertEqual(self.q("SELECT branch_id FROM invoices WHERE id = ?", (inv,))["branch_id"], gui)
        a.post(f"/staff/invoices/{inv}/branch", data={"branch_id": mal})
        # paid at Guiguinto: the payment counts there; the bill stays Malolos
        a.post(f"/staff/invoices/{inv}/payments", data={"action": "multi", "method": "cash", "amount": "5000", "received_at": "2026-10-31",
                                                        "received_branch_id": gui, "not_signed_reason": "test"})
        p = self.q("SELECT branch_id FROM payments WHERE invoice_id = ? AND status = 'valid'", (inv,))
        self.assertIsNotNone(p)
        self.assertEqual(p["branch_id"], gui)
        self.assertEqual(self.q("SELECT branch_id FROM invoices WHERE id = ?", (inv,))["branch_id"], mal)
        # with a payment the bill can't be moved
        a.post(f"/staff/invoices/{inv}/branch", data={"branch_id": gui})
        self.assertEqual(self.q("SELECT branch_id FROM invoices WHERE id = ?", (inv,))["branch_id"], mal)


class TestCollectionsByService(Base):
    def test_installment_on_old_bill_counts_by_payment_date(self):
        from app.util import now_str, today
        mal = self.branch("malolos")
        uid = self.q("SELECT id FROM users WHERE email LIKE 'dentist.malolos@%'")["id"]
        pid = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (mal,))["id"]
        inv = self.conn.insert("invoices", {"branch_id": mal, "patient_id": pid, "status": "issued", "number": "MM-CS1", "issued_at": "2024-01-04",
                                            "subtotal_cents": 4500000, "discount_cents": 0, "tax_cents": 0, "total_cents": 4500000,
                                            "created_at": now_str(), "legacy": 1})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Orthodontic Treatment (Metal Braces-Class 1)", "qty": 1,
                                           "unit_price_cents": 4500000, "discount_cents": 0, "amount_cents": 4500000, "dentist_id": uid})
        t = today().isoformat()
        a = self.login("admin")
        a.post(f"/staff/invoices/{inv}/payments", data={"action": "multi", "method": "cash", "amount": "1550", "received_at": t,
                                                        "not_signed_reason": "x", "received_branch_id": mal})
        page = a.get(f"/staff/reports/sales?from={t}&to={t}&branch={mal}").data.decode()
        self.assertIn("Collections by service", page)
        sec = page.split("Collections by service")[1].split("Collections by dentist")[0]
        self.assertIn("Braces, Aligners &amp; Orthodontics", sec)
        dsec = page.split("Collections by dentist")[1].split("Collections by method")[0]
        self.assertIn(self.q("SELECT name FROM users WHERE id = ?", (uid,))["name"], dsec)

    def test_change_payment_branch(self):
        from app.util import now_str, today
        mal, gui = self.branch("malolos"), self.branch("guiguinto")
        pid = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (mal,))["id"]
        inv = self.conn.insert("invoices", {"branch_id": mal, "patient_id": pid, "status": "issued", "number": "MM-PB1", "issued_at": "2024-01-04",
                                            "subtotal_cents": 4500000, "discount_cents": 0, "tax_cents": 0, "total_cents": 4500000, "created_at": now_str(), "legacy": 1})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Orthodontic Treatment", "qty": 1, "unit_price_cents": 4500000,
                                           "discount_cents": 0, "amount_cents": 4500000})
        t = today().isoformat()
        pay = self.conn.insert("payments", {"invoice_id": inv, "branch_id": mal, "kind": "payment", "amount_cents": 155000, "method": "bank_transfer",
                                            "account": "BPI", "received_at": t, "status": "valid", "created_at": now_str()})
        a = self.login("admin")
        self.assertIn("Change branch", a.get(f"/staff/invoices/{inv}").data.decode())
        a.post(f"/staff/invoices/{inv}/payments/{pay}/branch", data={"branch_id": gui})
        self.assertEqual(self.q("SELECT branch_id FROM payments WHERE id = ?", (pay,))["branch_id"], gui)
        from app import daily_report
        with self.app.app_context():
            reps = {r["branch"] if "branch" in r else i: r for i, r in enumerate(daily_report.build(self.conn, t))}
        self.assertIn("1,550", self.login("admin").get(f"/staff/reports/daily-collection?date={t}").data.decode())


class TestCalendarMonth(Base):
    def test_month_view_shows_patient_and_procedure(self):
        from app.util import today
        a = self.q("SELECT a.start_at, p.last_name, p.first_name, s.name AS service FROM appointments a JOIN patients p ON p.id = a.patient_id "
                   "JOIN services s ON s.id = a.service_id WHERE a.status != 'cancelled' ORDER BY a.start_at DESC LIMIT 1")
        page = self.login("admin").get(f"/staff/calendar?view=month&date={a['start_at'][:10]}").data.decode()
        self.assertIn("cal-month", page)
        from html import escape
        self.assertIn(escape(f"{a['last_name']}, {a['first_name']}", quote=False), page)
        self.assertIn(escape(a["service"], quote=False), page)

    def test_commission_sets_dentist_on_lines_without_one(self):
        from app.util import now_str, today
        from app.payroll import add_manual_commission
        uid = self.q("SELECT id FROM users WHERE email LIKE 'dentist.malolos@%'")["id"]
        emp = self.q("SELECT id FROM employees WHERE user_id = ?", (uid,))
        eid = emp["id"] if emp else self.conn.insert("employees", {"full_name": "Demo Dentist", "position": "Dentist", "employment_type": "regular",
                                                                    "user_id": uid, "active": 1, "created_at": now_str()})
        mal = self.branch("malolos")
        pid = self.conn.insert("patients", {"first_name": "Noset", "last_name": "Dentistline", "chart_no": "DH-NS1", "preferred_branch_id": mal,
                                            "created_at": now_str(), "updated_at": now_str()})
        inv = self.conn.insert("invoices", {"branch_id": mal, "patient_id": pid, "status": "issued", "number": "MM-NS1", "issued_at": "2024-01-04",
                                            "subtotal_cents": 4500000, "discount_cents": 0, "tax_cents": 0, "total_cents": 4500000, "created_at": now_str(), "legacy": 1})
        line = self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Orthodontic Treatment (Metal Braces-Class 1)", "qty": 1,
                                                  "unit_price_cents": 4500000, "discount_cents": 0, "amount_cents": 4500000})
        with self.app.app_context():
            add_manual_commission(self.conn, None, eid, today(), None, None, 20000, None, invoice_id=inv)
        self.assertEqual(self.q("SELECT dentist_id FROM invoice_items WHERE id = ?", (line,))["dentist_id"], uid)
        page = self.login("dentist.malolos").get("/staff/my-cases/?q=dentistline&from=2000-01-01").data.decode()
        self.assertIn("Dentistline, Noset", page)
        self.assertIn("commission ₱200.00", page)
        t = today().isoformat()
        self.assertIn("Dentistline, Noset", self.login("dentist.malolos").get(f"/staff/my-cases/?q=dentistline&from={t}&to={t}").data.decode())
