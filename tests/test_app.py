"""End-to-end checks of the acceptance criteria. Run: python -m unittest discover -s tests -v"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.db import standalone_connection  # noqa: E402
from app.migrate import run_migrations  # noqa: E402

PW = "DemoPass-2026"
DOMAIN = "@demo.dentalhaven.test"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        db_path = os.path.join(cls.tmp, "test.db")
        cls.app = create_app({"TESTING": True, "CSRF_DISABLED": True, "DATABASE_URL": f"sqlite:///{db_path}",
                              "UPLOAD_DIR": os.path.join(cls.tmp, "uploads"), "PUBLIC_RATE_LIMIT": 1000,
                              "PUBLIC_UPLOAD_DIR": os.path.join(cls.tmp, "public"), "IMPORT_DIR": os.path.join(cls.tmp, "imports"),
                              "DATA_DIR": cls.tmp})
        cls.conn = standalone_connection(cls.app.config["DATABASE_URL"])
        run_migrations(cls.conn, verbose=False)
        from app.seed import seed_demo
        with cls.app.app_context():
            seed_demo(cls.conn, PW)

    @classmethod
    def tearDownClass(cls):
        cls.conn.raw.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def login(self, who):
        c = self.app.test_client()
        r = c.post("/staff/login", data={"email": who + DOMAIN, "password": PW})
        self.assertEqual(r.status_code, 302, who)
        return c

    def q(self, sql, params=()):
        return self.conn.one(sql, params)

    def branch(self, slug):
        return self.q("SELECT id FROM branches WHERE slug = ?", (slug,))["id"]

    def next_weekday(self, weekday, weeks=3):
        d = datetime.now().date() + timedelta(days=7 * weeks)
        while d.weekday() != weekday:
            d += timedelta(days=1)
        return d


class TestAccessControl(Base):
    def test_only_super_admin_manages_users_and_roles(self):
        for who in ("dentist.malolos", "staff.malolos", "reception.malolos"):
            c = self.login(who)
            self.assertEqual(c.get("/staff/admin/users").status_code, 403)
            self.assertEqual(c.post("/staff/admin/users/new", data={"name": "X", "email": "x@x.test", "role": "super_admin"}).status_code, 403)
            self.assertEqual(c.post("/staff/admin/roles", data={"grant": "receptionist:billing.view"}).status_code, 403)
        self.assertIsNone(self.q("SELECT id FROM users WHERE email = 'x@x.test'"))

    def test_locked_permissions_cannot_be_granted(self):
        c = self.login("admin")
        current = [f"{r['role']}:{r['permission']}" for r in self.conn.all("SELECT * FROM role_permissions")]
        r = c.post("/staff/admin/roles", data={"grant": current + ["receptionist:users.manage", "staff:roles.manage"]})
        self.assertEqual(r.status_code, 302)
        self.assertIsNone(self.q("SELECT 1 AS x FROM role_permissions WHERE permission IN ('users.manage','roles.manage')"))

    def test_user_creation_is_audited_and_least_privilege(self):
        c = self.login("admin")
        r = c.post("/staff/admin/users/new", data={"name": "New Recep", "email": "new.recep@clinic.test", "role": "receptionist",
                                                   "branches": [str(self.branch("bocaue"))]})
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"shown only once", r.data)
        u = self.q("SELECT * FROM users WHERE email = 'new.recep@clinic.test'")
        self.assertEqual(u["must_change_password"], 1)
        self.assertIsNotNone(self.q("SELECT id FROM audit_log WHERE action = 'user_created' AND entity_id = ?", (u["id"],)))
        # role change audited
        c.post(f"/staff/admin/users/{u['id']}", data={"name": "New Recep", "email": "new.recep@clinic.test", "role": "staff",
                                                     "branches": [str(self.branch("bocaue"))], "active": "1"})
        self.assertIsNotNone(self.q("SELECT id FROM audit_log WHERE action = 'role_changed' AND entity_id = ?", (u["id"],)))

    def test_super_admin_cannot_change_own_role(self):
        c = self.login("admin")
        me = self.q("SELECT * FROM users WHERE email = ?", ("admin" + DOMAIN,))
        c.post(f"/staff/admin/users/{me['id']}", data={"name": me["name"], "email": me["email"], "role": "receptionist", "active": "1",
                                                      "branches": [str(self.branch("malolos"))]})
        self.assertEqual(self.q("SELECT role FROM users WHERE id = ?", (me["id"],))["role"], "super_admin")

    def test_branch_scoping(self):
        bocaue = self.branch("bocaue")
        p = self.q("SELECT p.id FROM patients p WHERE p.preferred_branch_id = ? AND NOT EXISTS (SELECT 1 FROM appointments a JOIN branches b ON b.id=a.branch_id "
                   "WHERE a.patient_id = p.id AND b.slug IN ('malolos')) AND NOT EXISTS (SELECT 1 FROM invoices i JOIN branches b ON b.id=i.branch_id "
                   "WHERE i.patient_id = p.id AND b.slug = 'malolos') LIMIT 1", (bocaue,))
        c = self.login("reception.malolos")
        self.assertEqual(c.get(f"/staff/patients/{p['id']}").status_code, 403)
        c2 = self.login("reception.bocaue")
        self.assertEqual(c2.get(f"/staff/patients/{p['id']}").status_code, 200)

    def test_branch_switcher_limits_to_authorised(self):
        c = self.login("staff.malolos")
        self.assertEqual(c.post("/staff/branch", data={"branch_id": str(self.branch("sjdm"))}).status_code, 403)
        self.assertEqual(c.post("/staff/branch", data={"branch_id": str(self.branch("guiguinto"))}).status_code, 302)

    def test_front_desk_sees_alert_not_clinical(self):
        p = self.q("SELECT p.id, p.alert_flag FROM patients p JOIN branches b ON b.id = p.preferred_branch_id WHERE b.slug='malolos' AND p.alert_flag != '' LIMIT 1")
        c = self.login("reception.malolos")
        r = c.get(f"/staff/patients/{p['id']}")
        self.assertEqual(r.status_code, 200)
        self.assertIn(p["alert_flag"].encode(), r.data)
        self.assertNotIn(b"Synthetic demo history", r.data)
        self.assertEqual(c.get(f"/staff/patients/{p['id']}?tab=clinical").status_code, 403)

    def test_dentist_only_assigned_patients(self):
        d = self.q("SELECT id FROM users WHERE email = ?", ("dentist.sjdm" + DOMAIN,))
        other = self.q("SELECT id FROM patients WHERE id NOT IN (SELECT patient_id FROM patient_assignments WHERE dentist_id = ?) LIMIT 1", (d["id"],))
        mine = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (d["id"],))
        c = self.login("dentist.sjdm")
        self.assertIn(c.get(f"/staff/patients/{other['id']}?tab=clinical").status_code, (403, 404))
        r = c.get(f"/staff/patients/{mine['id']}?tab=clinical")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Synthetic demo history", r.data)

    def test_csrf_enforced(self):
        app = create_app({"TESTING": True, "DATABASE_URL": self.app.config["DATABASE_URL"], "UPLOAD_DIR": self.app.config["UPLOAD_DIR"]})
        c = app.test_client()
        self.assertEqual(c.post("/staff/login", data={"email": "admin" + DOMAIN, "password": PW}).status_code, 400)


class TestBooking(Base):
    def _slot(self, c, branch_id, service_id, day):
        r = c.get(f"/book/slots?branch_id={branch_id}&service_id={service_id}&date={day.isoformat()}")
        return r.get_json()["slots"]

    def test_public_request_stays_pending(self):
        c = self.app.test_client()
        b = self.branch("guiguinto")
        svc = self.q("SELECT id FROM services WHERE slug='general-dentistry'")["id"]
        day = self.next_weekday(1)
        slots = self._slot(c, b, svc, day)
        self.assertTrue(slots)
        before = self.q("SELECT COUNT(*) AS n FROM appointments")["n"]
        r = c.post("/book", data={"branch_id": b, "service_id": svc, "date": day.isoformat(), "time": slots[0], "full_name": "Test Person",
                                  "phone": "0900 999 0001", "consent_privacy": "1", "started": "0"}, follow_redirects=True)
        self.assertIn(b"not yet a confirmed appointment", r.data)
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM appointments")["n"], before)
        req = self.q("SELECT * FROM booking_requests WHERE full_name = 'Test Person'")
        self.assertEqual(req["status"], "pending")

    def test_consent_required(self):
        c = self.app.test_client()
        r = c.post("/book", data={"branch_id": self.branch("malolos"), "service_id": 1, "date": self.next_weekday(1).isoformat(),
                                  "time": "10:00", "full_name": "No Consent", "phone": "0900 999 0002", "started": "0"})
        self.assertIn(b"agree to the privacy notice", r.data)
        self.assertIsNone(self.q("SELECT id FROM booking_requests WHERE full_name = 'No Consent'"))

    def test_staff_confirm_request_and_conflicts(self):
        c = self.login("reception.malolos")
        malolos = self.branch("malolos")
        dentist = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        day = self.next_weekday(0, weeks=4)  # Monday: dentist.malolos works at Malolos
        patient = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (malolos,))["id"]
        svc = self.q("SELECT id FROM services WHERE slug='general-dentistry'")["id"]
        form = {"patient_id": patient, "branch_id": malolos, "service_id": svc, "dentist_id": dentist, "date": day.isoformat(),
                "time": "16:00", "status": "confirmed", "source": "phone"}
        r = c.post("/staff/appointments/new", data=form)
        self.assertEqual(r.status_code, 302)
        first = self.q("SELECT * FROM appointments WHERE dentist_id = ? AND start_at = ?", (dentist, f"{day.isoformat()} 16:00"))
        self.assertIsNotNone(first)
        # same dentist, overlapping time → rejected
        form2 = dict(form, time="16:15")
        r = c.post("/staff/appointments/new", data=form2)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Conflict", r.data)
        self.assertIsNone(self.q("SELECT id FROM appointments WHERE start_at = ? AND dentist_id = ?", (f"{day.isoformat()} 16:15", dentist)))
        # outside branch hours → rejected
        r = c.post("/staff/appointments/new", data=dict(form, time="19:00"))
        self.assertIn(b"Outside branch hours", r.data)
        # rooms: fill both chairs with no dentist then a third is rejected
        for t in ("11:00",):
            for _ in range(2):
                c.post("/staff/appointments/new", data=dict(form, dentist_id="", time=t))
            r = c.post("/staff/appointments/new", data=dict(form, dentist_id="", time=t))
            self.assertIn(b"All rooms", r.data)
        # reschedule into conflict is rejected
        other = c.post("/staff/appointments/new", data=dict(form, time="14:00"))
        second = self.q("SELECT * FROM appointments WHERE dentist_id = ? AND start_at = ?", (dentist, f"{day.isoformat()} 14:00"))
        r = c.post(f"/staff/appointments/{second['id']}/reschedule", data=dict(form, time="16:00"), follow_redirects=True)
        self.assertIn(b"Couldn", r.data)
        self.assertEqual(self.q("SELECT start_at FROM appointments WHERE id = ?", (second["id"],))["start_at"], f"{day.isoformat()} 14:00")
        # status workflow
        self.assertEqual(c.post(f"/staff/appointments/{first['id']}/status", data={"status": "checked_in"}).status_code, 302)
        c.post(f"/staff/appointments/{first['id']}/status", data={"status": "completed", "followup_days": "7"})
        self.assertEqual(self.q("SELECT status FROM appointments WHERE id = ?", (first["id"],))["status"], "completed")
        self.assertIsNotNone(self.q("SELECT id FROM follow_ups WHERE appointment_id = ? AND kind='post_treatment'", (first["id"],)))
        # cancel requires reason
        c.post(f"/staff/appointments/{second['id']}/status", data={"status": "cancelled"})
        self.assertEqual(self.q("SELECT status FROM appointments WHERE id = ?", (second["id"],))["status"], "confirmed")
        c.post(f"/staff/appointments/{second['id']}/status", data={"status": "cancelled", "reason": "Patient asked"})
        self.assertEqual(self.q("SELECT status FROM appointments WHERE id = ?", (second["id"],))["status"], "cancelled")

    def test_confirm_booking_request_creates_patient_and_appointment(self):
        c = self.login("admin")
        req = self.q("SELECT * FROM booking_requests WHERE status='pending' AND ref_code LIKE 'DH-DEMO%' LIMIT 1")
        day = self.next_weekday(2, weeks=5)
        r = c.post(f"/staff/requests/{req['id']}", data={"action": "confirm", "patient_id": "", "branch_id": req["branch_id"],
                                                       "service_id": req["service_id"], "dentist_id": "", "date": day.isoformat(), "time": "10:30"})
        self.assertEqual(r.status_code, 302, r.data[:500])
        req2 = self.q("SELECT * FROM booking_requests WHERE id = ?", (req["id"],))
        self.assertEqual(req2["status"], "confirmed")
        self.assertEqual(self.q("SELECT status FROM appointments WHERE id = ?", (req2["appointment_id"],))["status"], "confirmed")

    def test_reminders_respect_opt_out(self):
        rows = self.conn.all("SELECT r.status, p.opt_out_all, p.contact_sms FROM reminders r JOIN patients p ON p.id = r.patient_id")
        self.assertTrue(rows)
        for r in rows:
            if r["opt_out_all"]:
                self.assertEqual(r["status"], "skipped_opt_out")
            elif not r["contact_sms"]:
                self.assertEqual(r["status"], "skipped_no_consent")
        self.assertIsNone(self.q("SELECT id FROM reminders WHERE status = 'sent_provider'"))


class TestBillingAndReports(Base):
    def test_invoice_payment_refund_void_and_reports(self):
        c = self.login("staff.malolos")
        malolos = self.branch("malolos")
        p = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (malolos,))["id"]
        r = c.post("/staff/invoices/new", data={"patient_id": p, "branch_id": malolos})
        inv_id = int(re.search(r"/invoices/(\d+)", r.headers["Location"]).group(1))
        c.post(f"/staff/invoices/{inv_id}/edit", data={"action": "add_item", "description": "Test item", "qty": "2", "unit_price": "1,000.00"})
        c.post(f"/staff/invoices/{inv_id}/edit", data={"action": "issue"})
        inv = self.q("SELECT * FROM invoices WHERE id = ?", (inv_id,))
        self.assertEqual(inv["status"], "issued")
        self.assertEqual(inv["total_cents"], 200000)
        self.assertTrue(inv["number"].startswith("MAL-"))
        # overpayment rejected; payment accepted
        c.post(f"/staff/invoices/{inv_id}/payments", data={"action": "payment", "amount": "5000", "method": "cash"})
        self.assertIsNone(self.q("SELECT id FROM payments WHERE invoice_id = ?", (inv_id,)))
        c.post(f"/staff/invoices/{inv_id}/payments", data={"action": "payment", "amount": "1500", "method": "gcash"})
        self.assertEqual(self.q("SELECT SUM(amount_cents) AS s FROM payments WHERE invoice_id = ?", (inv_id,))["s"], 150000)
        # staff lacks billing.void by default
        self.assertEqual(c.post(f"/staff/invoices/{inv_id}/payments", data={"action": "refund", "amount": "100", "method": "cash", "notes": "x"}).status_code, 403)
        self.assertEqual(c.post(f"/staff/invoices/{inv_id}/void", data={"reason": "x"}).status_code, 403)
        a = self.login("admin")
        a.post(f"/staff/invoices/{inv_id}/void", data={"reason": "test"})
        self.assertEqual(self.q("SELECT status FROM invoices WHERE id = ?", (inv_id,))["status"], "issued")  # blocked: has payments
        a.post(f"/staff/invoices/{inv_id}/payments", data={"action": "refund", "amount": "1500", "method": "gcash", "notes": "Refund test"})
        a.post(f"/staff/invoices/{inv_id}/void", data={"reason": "test"})
        self.assertEqual(self.q("SELECT status FROM invoices WHERE id = ?", (inv_id,))["status"], "void")
        self.assertIsNotNone(self.q("SELECT id FROM audit_log WHERE action = 'invoice_voided' AND entity_id = ?", (inv_id,)))
        # reports: sales exclude voids; collections are net of refunds
        today = datetime.now().date().isoformat()
        r = a.get(f"/staff/reports/export/sales.csv?from={today}&to={today}&branch={malolos}")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Net collections", r.data)
        self.assertIn(b"Malolos", r.data)

    def test_reports_forbidden_without_permission(self):
        c = self.login("reception.malolos")
        self.assertEqual(c.get("/staff/reports/sales").status_code, 403)
        self.assertEqual(c.get("/staff/reports/export/sales.csv").status_code, 403)


class TestPayrollAndReportCards(Base):
    def test_payroll_cannot_be_approved_until_rules_confirmed(self):
        c = self.login("admin")
        pp = self.q("SELECT * FROM payroll_periods LIMIT 1")
        c.post(f"/staff/payroll/{pp['id']}", data={"action": "submit"})
        self.assertEqual(self.q("SELECT status FROM payroll_periods WHERE id = ?", (pp["id"],))["status"], "submitted")
        r = c.post(f"/staff/payroll/{pp['id']}", data={"action": "approve"}, follow_redirects=True)
        self.assertIn(b"pay rules aren", r.data)
        self.assertEqual(self.q("SELECT status FROM payroll_periods WHERE id = ?", (pp["id"],))["status"], "submitted")
        r = c.get(f"/staff/payroll/{pp['id']}")
        self.assertIn(b"DRAFT, NOT FINAL PAYROLL", r.data)

    def test_dtr_correction_requires_reason_and_is_audited(self):
        c = self.login("admin")
        rec = self.q("SELECT * FROM time_records WHERE status = 'exception' LIMIT 1")
        c.post(f"/staff/attendance/{rec['id']}/correct", data={"action": "correct", "time_in": "09:00", "time_out": "18:00", "reason": ""})
        self.assertEqual(self.q("SELECT status FROM time_records WHERE id = ?", (rec["id"],))["status"], "exception")
        c.post(f"/staff/attendance/{rec['id']}/correct", data={"action": "correct", "time_in": "09:00", "time_out": "18:00", "reason": "Verified"})
        self.assertEqual(self.q("SELECT status FROM time_records WHERE id = ?", (rec["id"],))["status"], "corrected")
        self.assertIsNotNone(self.q("SELECT id FROM audit_log WHERE action = 'dtr_corrected' AND entity_id = ?", (rec["id"],)))

    def test_report_card_requires_dentist_review(self):
        rc = self.q("SELECT * FROM report_cards LIMIT 1")
        reviewer = self.q("SELECT email FROM users WHERE id = ?", (rc["reviewer_id"],))["email"].split("@")[0]
        a = self.login("admin")
        self.assertEqual(a.post(f"/staff/report-cards/{rc['id']}", data={"action": "approve", "summary": "x", "recommendations": "y"}).status_code, 403)
        self.assertIn(b"DO NOT GIVE TO THE PATIENT", a.get(f"/staff/report-cards/{rc['id']}/print").data)
        d = self.login(reviewer)
        r = d.post(f"/staff/report-cards/{rc['id']}", data={"action": "approve", "summary": rc["summary"], "recommendations": rc["recommendations"]},
                   follow_redirects=True)
        self.assertIn(b"placeholder", r.data)  # the [Dentist: ...] placeholder must be replaced
        d.post(f"/staff/report-cards/{rc['id']}", data={"action": "approve", "summary": "All good.", "recommendations": "Brush twice daily."})
        self.assertEqual(self.q("SELECT status FROM report_cards WHERE id = ?", (rc["id"],))["status"], "approved")
        self.assertNotIn(b"DO NOT GIVE", d.get(f"/staff/report-cards/{rc['id']}/print").data)


class TestPublicSite(Base):
    def test_pages_render_with_placeholders(self):
        c = self.app.test_client()
        for path in ("/", "/services/dental-implants", "/branches/sjdm", "/laboratory", "/gallery", "/feedback", "/privacy", "/book", "/inquire"):
            r = c.get(path)
            self.assertEqual(r.status_code, 200, path)
        self.assertIn(b"to be confirmed", c.get("/branches/sjdm").data)
        self.assertIn(b"Content-Security-Policy", str(c.get("/").headers).encode())

    def test_inquiry_creates_lead(self):
        c = self.app.test_client()
        c.post("/inquire", data={"full_name": "Lead Person", "phone": "0900 999 0003", "message": "Do you do implants?",
                                 "consent_privacy": "1", "started": "0"})
        lead = self.q("SELECT * FROM leads WHERE full_name = 'Lead Person'")
        self.assertEqual(lead["source"], "website")
        self.assertEqual(lead["status"], "new")


if __name__ == "__main__":
    unittest.main()
