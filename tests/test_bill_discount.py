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
        from app import daily_report
        def gross(bid):
            with self.app.app_context():
                b = self.q("SELECT * FROM branches WHERE id = ?", (bid,))
                r = daily_report.branch_report(self.conn, b, t)
            return sum(v for k, v in r.items() if k in ("gross_total",)) if "gross_total" in r else r
        g_before, m_before = gross(gui), gross(mal)
        a = self.login("admin")
        self.assertIn("Change branch", a.get(f"/staff/invoices/{inv}").data.decode())
        a.post(f"/staff/invoices/{inv}/payments/{pay}/branch", data={"branch_id": gui})
        self.assertEqual(self.q("SELECT branch_id FROM payments WHERE id = ?", (pay,))["branch_id"], gui)
        if isinstance(g_before, int):
            self.assertEqual(gross(gui) - g_before, 155000)
            self.assertEqual(m_before - gross(mal), 155000)


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


class TestOverlapBooking(Base):
    def test_overlap_only_when_ticked(self):
        from datetime import date, timedelta
        did = self.q("SELECT id FROM users WHERE email LIKE 'dentist.malolos@%'")["id"]
        b = self.branch("malolos")
        pid = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (b,))["id"]
        svc = self.q("SELECT id FROM services WHERE active = 1 LIMIT 1")["id"]
        sched = self.q("SELECT weekday, start_time FROM dentist_schedules WHERE dentist_id = ? AND branch_id = ? LIMIT 1", (did, b))
        d = date.today() + timedelta(days=21)
        while d.weekday() != sched["weekday"]:
            d += timedelta(days=1)
        c = self.login("reception.malolos")
        base = {"patient_id": pid, "branch_id": b, "service_id": svc, "dentist_id": did, "date": d.isoformat(), "status": "confirmed", "source": "staff"}
        n0 = self.conn.scalar("SELECT COUNT(*) FROM appointments WHERE dentist_id = ? AND substr(start_at, 1, 10) = ?", (did, d.isoformat()))
        c.post(f"/staff/appointments/new?patient_id={pid}", data={**base, "time": "10:00", "duration": "30"})
        r = c.post(f"/staff/appointments/new?patient_id={pid}", data={**base, "time": "10:20", "duration": "40"})
        self.assertIn("Allow overlap", r.data.decode())
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM appointments WHERE dentist_id = ? AND substr(start_at, 1, 10) = ?", (did, d.isoformat())), n0 + 1)
        c.post(f"/staff/appointments/new?patient_id={pid}", data={**base, "time": "10:20", "duration": "40", "allow_overlap": "1"})
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM appointments WHERE dentist_id = ? AND substr(start_at, 1, 10) = ?", (did, d.isoformat())), n0 + 2)


class TestPatientSuggest(Base):
    def test_suggest_while_typing(self):
        p = self.q("SELECT p.id, p.first_name, p.last_name FROM patients p WHERE p.preferred_branch_id = ? AND p.active = 1 LIMIT 1", (self.branch("malolos"),))
        c = self.login("reception.malolos")
        self.assertIn("data-suggest", c.get("/staff/appointments/new").data.decode())
        rows = c.post("/staff/appointments/patient-suggest", data={"q": p["last_name"][:4]}).get_json()
        self.assertTrue(any(r["name"] == f"{p['last_name']}, {p['first_name']}" for r in rows))
        self.assertTrue(all("phone" not in r for r in rows))
        self.assertEqual(c.post("/staff/appointments/patient-suggest", data={"q": "a"}).get_json(), [])
        self.assertEqual(self.login("dentist.malolos").post("/staff/appointments/patient-suggest", data={"q": "ab"}).status_code, 403)

    def test_top_bar_search(self):
        c = self.login("reception.malolos")
        page = c.get("/staff/").data.decode()
        self.assertIn('id="top-q"', page)
        p = self.q("SELECT first_name, last_name FROM patients WHERE preferred_branch_id = ? AND active = 1 LIMIT 1", (self.branch("malolos"),))
        res = c.post("/staff/patients/suggest", data={"q": p["last_name"]}).get_json()["results"]
        self.assertTrue(res)
        r = c.post("/staff/patients/", data={"q": p["last_name"]})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('id="top-q"', self.login("technician.malolos").get("/staff/").data.decode()) if self.q("SELECT id FROM users WHERE email LIKE 'technician.malolos@%'") else None


class TestProgressNoteBillLines(Base):
    def test_dash_names_match_and_duplicate_line_removed(self):
        from app.util import now_str
        mal = self.branch("malolos")
        pid = self.conn.insert("patients", {"first_name": "Dash", "last_name": "Matchtest", "chart_no": "DH-DM1", "preferred_branch_id": mal,
                                            "created_at": now_str(), "updated_at": now_str()})
        self.conn.insert("procedures", {"patient_id": pid, "description": "Oral Prophylaxis (Moderate) -\nNote", "status": "completed",
                                        "performed_at": "2026-09-07", "created_at": now_str(), "legacy_key": "pn-dm-1"})
        inv = self.conn.insert("invoices", {"branch_id": mal, "patient_id": pid, "status": "issued", "number": "MM-DM1", "issued_at": "2026-09-07",
                                            "subtotal_cents": 8600000, "discount_cents": 0, "tax_cents": 0, "total_cents": 8600000, "created_at": now_str(), "legacy": 1})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Oral Prophylaxis (Moderate)", "qty": 1, "unit_price_cents": 200000,
                                           "discount_cents": 0, "amount_cents": 200000, "done_on": "2026-09-07"})
        dup1 = self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Root Canal Treatment", "qty": 1, "unit_price_cents": 4200000,
                                                  "discount_cents": 0, "amount_cents": 4200000, "done_on": "2026-09-07"})
        dup2 = self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Root Canal Treatment", "qty": 1, "unit_price_cents": 4200000,
                                                  "discount_cents": 0, "amount_cents": 4200000, "done_on": "2026-09-07"})
        a = self.login("admin")
        page = a.get(f"/staff/patients/{pid}?tab=notes").data.decode()
        row = page.split("Oral Prophylaxis (Moderate) -")[1][:300]
        self.assertIn("₱2,000.00", row)                        # matched with its bill line
        self.assertIn(f'id="bp{dup2}"', page)                   # bill-only line: editable
        a.post(f"/staff/invoices/{inv}/items/{dup2}/fix", data={"action": "remove"})
        self.assertIsNone(self.q("SELECT id FROM invoice_items WHERE id = ?", (dup2,)))
        self.assertEqual(self.q("SELECT total_cents FROM invoices WHERE id = ?", (inv,))["total_cents"], 4400000)
        a.post(f"/staff/invoices/{inv}/items/{dup1}/fix", data={"action": "price", "price": "10500"})
        self.assertEqual(self.q("SELECT total_cents FROM invoices WHERE id = ?", (inv,))["total_cents"], 1250000)
        self.conn.insert("payments", {"invoice_id": inv, "branch_id": mal, "kind": "payment", "amount_cents": 1000, "method": "cash",
                                      "received_at": now_str(), "status": "valid", "created_at": now_str()})
        a.post(f"/staff/invoices/{inv}/items/{dup1}/fix", data={"action": "price", "price": "1"})
        self.assertEqual(self.q("SELECT total_cents FROM invoices WHERE id = ?", (inv,))["total_cents"], 1250000)


class TestMymedsPaidOnNewBill(Base):
    def test_reentered_bill_marked_paid_on_work_date(self):
        from app.util import now_str
        gui = self.branch("guiguinto")
        pid = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (gui,))["id"]
        inv = self.conn.insert("invoices", {"branch_id": gui, "patient_id": pid, "status": "issued", "number": "GUI-T-11", "issued_at": "2026-11-02",
                                            "subtotal_cents": 4650000, "discount_cents": 0, "tax_cents": 0, "total_cents": 4650000, "created_at": now_str()})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "RCT - RETREATMENT", "qty": 1, "unit_price_cents": 4650000,
                                           "discount_cents": 0, "amount_cents": 4650000, "done_on": "2026-09-07"})
        a = self.login("admin")
        page = a.get(f"/staff/invoices/{inv}").data.decode()
        self.assertIn("Paid in MyMedsPH", page)
        self.assertIn('value="2026-09-07"', page)
        a.post(f"/staff/invoices/{inv}/mymeds-paid", data={"amount": "46500", "paid_on": "2026-09-07"})
        p = self.q("SELECT * FROM payments WHERE invoice_id = ? AND status = 'valid'", (inv,))
        self.assertEqual((p["amount_cents"], p["received_at"][:10], p["method"]), (4650000, "2026-09-07", "mymeds"))


class TestCommissionReport(Base):
    def test_cutoff_report_and_access(self):
        from app.util import now_str
        uid = self.q("SELECT id FROM users WHERE email LIKE 'dentist.malolos@%'")["id"]
        emp = self.q("SELECT id FROM employees WHERE user_id = ?", (uid,))
        eid = emp["id"] if emp else self.conn.insert("employees", {"full_name": "Demo Dentist", "position": "Dentist", "employment_type": "regular",
                                                                    "user_id": uid, "active": 1, "created_at": now_str()})
        mal = self.branch("malolos")
        pid = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (mal,))["id"]
        inv = self.conn.insert("invoices", {"branch_id": mal, "patient_id": pid, "status": "issued", "number": "CR-1", "issued_at": "2026-10-10",
                                            "subtotal_cents": 300000, "discount_cents": 0, "tax_cents": 0, "total_cents": 300000, "created_at": now_str()})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Root canal (demo)", "qty": 1, "unit_price_cents": 300000,
                                           "discount_cents": 0, "amount_cents": 300000, "dentist_id": uid, "done_on": "2026-10-10"})
        self.conn.insert("dentist_commissions", {"employee_id": eid, "earned_on": "2026-10-10", "invoice_id": inv, "base_cents": 300000,
                                                 "rate_bp": 3000, "amount_cents": 90000, "status": "valid", "created_at": now_str()})
        self.conn.insert("dentist_commissions", {"employee_id": eid, "earned_on": "2026-10-20", "invoice_id": inv, "amount_cents": 5000,
                                                 "status": "valid", "created_at": now_str()})
        a = self.login("admin")
        page = a.get("/staff/commissions/?month=2026-10&half=1").data.decode()
        self.assertIn("Dentist commissions", page)
        self.assertIn("₱900.00", page)
        self.assertNotIn("₱50.00", page)                       # 2nd cutoff entry not in the 1st
        self.assertIn("₱50.00", a.get("/staff/commissions/?month=2026-10&half=2").data.decode())
        self.conn.insert("dentist_commissions", {"employee_id": eid, "earned_on": "2026-10-25", "invoice_id": inv, "amount_cents": 0,
                                                 "base_cents": 10000, "description": "Zero entry (demo)", "status": "valid", "created_at": now_str()})
        self.assertNotIn("Zero entry (demo)", a.get("/staff/commissions/?month=2026-10&half=2").data.decode())   # ₱0 entries hidden
        csv =a.get("/staff/commissions/?month=2026-10&half=1&format=csv").data.decode()
        self.assertIn("Root canal (demo)", csv)
        self.assertEqual(self.login("staff.malolos").get("/staff/commissions/").status_code, 403)
        self.assertEqual(self.login("dentist.malolos").get("/staff/commissions/").status_code, 403)


class TestCollectionsList(Base):
    def test_list_by_date_with_patient_procedure_method_dentist(self):
        from app.util import now_str
        uid = self.q("SELECT id FROM users WHERE email LIKE 'dentist.malolos@%'")["id"]
        doc = self.q("SELECT name FROM users WHERE id = ?", (uid,))["name"]
        mal = self.branch("malolos")
        pt = self.q("SELECT * FROM patients WHERE preferred_branch_id = ? LIMIT 1", (mal,))
        inv = self.conn.insert("invoices", {"branch_id": mal, "patient_id": pt["id"], "status": "issued", "number": "CL-1", "issued_at": "2026-09-01",
                                            "subtotal_cents": 500000, "discount_cents": 0, "tax_cents": 0, "total_cents": 500000, "created_at": now_str()})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Braces adjustment (demo)", "qty": 1, "unit_price_cents": 500000,
                                           "discount_cents": 0, "amount_cents": 500000, "dentist_id": uid, "done_on": "2026-09-01"})
        for amt, d in ((150000, "2026-10-05"), (70000, "2026-10-06")):
            self.conn.insert("payments", {"invoice_id": inv, "branch_id": mal, "kind": "payment", "amount_cents": amt, "method": "cash",
                                          "received_at": d, "status": "valid", "created_at": now_str()})
        a = self.login("admin")
        page = a.get(f"/staff/reports/sales?from=2026-10-05&to=2026-10-05&branch={mal}").data.decode()
        self.assertIn("Collections list", page)
        self.assertIn(pt["last_name"], page)
        self.assertIn("Braces adjustment (demo)", page)
        self.assertIn(doc, page)
        self.assertIn("₱1,500.00", page)
        self.assertNotIn("₱700.00", page)                     # the next day's payment isn't in this day's list
        csv = a.get(f"/staff/reports/export/collections.csv?from=2026-10-05&to=2026-10-06&branch={mal}").data.decode()
        self.assertIn("Braces adjustment (demo)", csv)
        self.assertIn("Cash,1500.0", csv)
        self.assertIn("Cash,700.0", csv)
