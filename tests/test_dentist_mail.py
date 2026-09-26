"""Dentist appointment emails. SMTP is replaced by a fake: nothing is sent anywhere."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402

SENT = []


class FakeSMTP:
    fail = False

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        pass

    def login(self, user, pw):
        assert pw == "abcdefghijklmnop"
        FakeSMTP.last_login = user

    def send_message(self, msg):
        if FakeSMTP.fail:
            raise OSError("network unreachable")
        SENT.append(msg)


MAIL_ENV = {"MAIL_USERNAME": "clinic.notify@example.test", "MAIL_PASSWORD": "abcd efgh ijkl mnop"}


class TestDentistEmails(Base):
    def setUp(self):
        SENT.clear()
        FakeSMTP.fail = False
        self.malolos = self.branch("malolos")
        self.d1 = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        self.d2 = self.q("SELECT id FROM users WHERE email = ?", ("dentist.bocaue" + DOMAIN,))["id"]
        self.svc = self.q("SELECT id FROM services WHERE slug='general-dentistry'")["id"]
        self.patient = self.q("SELECT * FROM patients WHERE preferred_branch_id = ? LIMIT 1", (self.malolos,))
        self.conn.execute("UPDATE users SET notify_email = 1")
        self.conn.execute("UPDATE patients SET email = ''")  # patient emails are covered in test_patient_notify.py

    def _form(self, day, time, dentist):
        return {"patient_id": self.patient["id"], "branch_id": self.malolos, "service_id": self.svc, "dentist_id": dentist,
                "date": day.isoformat(), "time": time, "status": "confirmed", "source": "phone"}

    def _emails(self, appt_id):
        return self.conn.all("SELECT * FROM dentist_emails WHERE appointment_id = ? ORDER BY id", (appt_id,))

    def test_not_set_up_records_but_sends_nothing(self):
        c = self.login("reception.malolos")
        day = self.next_weekday(0, weeks=7)
        with mock.patch("smtplib.SMTP", FakeSMTP), mock.patch.dict(os.environ, {"MAIL_USERNAME": "", "MAIL_PASSWORD": ""}):
            c.post("/staff/appointments/new", data=self._form(day, "09:00", self.d1))
        a = self.q("SELECT id FROM appointments WHERE dentist_id = ? AND start_at = ?", (self.d1, f"{day} 09:00"))
        self.assertEqual([e["status"] for e in self._emails(a["id"])], ["not_set_up"])
        self.assertEqual(SENT, [])
        page = self.login("admin").get(f"/staff/appointments/{a['id']}")
        self.assertIn(b"Not sent (email not set up)", page.data)

    def test_booked_rescheduled_reassigned_cancelled(self):
        c = self.login("reception.malolos")
        monday = self.next_weekday(0, weeks=8)
        friday = self.next_weekday(4, weeks=8)
        with mock.patch("smtplib.SMTP", FakeSMTP), mock.patch.dict(os.environ, MAIL_ENV):
            c.post("/staff/appointments/new", data=self._form(monday, "10:00", self.d1))
            a = self.q("SELECT * FROM appointments WHERE dentist_id = ? AND start_at = ?", (self.d1, f"{monday} 10:00"))
            self.assertEqual(len(SENT), 1)
            msg = SENT[0]
            body = msg.get_content()
            self.assertEqual(msg["To"], "dentist.malolos" + DOMAIN)
            self.assertIn("New appointment", msg["Subject"])
            self.assertNotIn(self.patient["last_name"], msg["Subject"])  # no patient name on the lock screen
            for part in (self.patient["first_name"], self.patient["last_name"], "Preventive", "Malolos", "10:00 AM", "Monday"):
                self.assertIn(part, body)
            # reschedule the time → "rescheduled" with the old slot
            c.post(f"/staff/appointments/{a['id']}/reschedule", data=self._form(monday, "13:00", self.d1))
            self.assertEqual(len(SENT), 2)
            self.assertIn("rescheduled", SENT[1]["Subject"])
            self.assertIn("Previously:", SENT[1].get_content())
            self.assertIn("10:00 AM", SENT[1].get_content())
            # room-only / no real change → no email
            c.post(f"/staff/appointments/{a['id']}/reschedule", data=self._form(monday, "13:00", self.d1))
            self.assertEqual(len(SENT), 2)
            # move to another dentist → old dentist told, new dentist gets "new appointment"
            c.post(f"/staff/appointments/{a['id']}/reschedule", data=self._form(friday, "10:00", self.d2))
            self.assertEqual(self.q("SELECT dentist_id FROM appointments WHERE id = ?", (a["id"],))["dentist_id"], self.d2)
            self.assertEqual([(m["To"], m["Subject"].split(":")[0]) for m in SENT[2:]],
                             [("dentist.malolos" + DOMAIN, "Appointment moved to another dentist"),
                              ("dentist.bocaue" + DOMAIN, "New appointment")])
            # cancel → the current dentist is told
            c.post(f"/staff/appointments/{a['id']}/status", data={"status": "cancelled", "reason": "Patient asked"})
            self.assertEqual(SENT[-1]["To"], "dentist.bocaue" + DOMAIN)
            self.assertIn("cancelled", SENT[-1]["Subject"])
            self.assertNotIn("Patient asked", SENT[-1].get_content())  # internal reason isn't emailed
        self.assertEqual([e["status"] for e in self._emails(a["id"])], ["sent"] * 5)

    def test_approving_online_request_emails_chosen_dentist(self):
        c = self.login("reception.malolos")
        monday = self.next_weekday(0, weeks=9)
        rid = self.conn.insert("booking_requests", {
            "ref_code": "DH-TEST-MAIL1", "full_name": "Test Requester", "phone": "0900 000 1234", "branch_id": self.malolos,
            "service_id": self.svc, "dentist_id": self.d1, "preferred_start": f"{monday} 11:00", "consent_privacy": 1,
            "status": "pending", "created_at": "2026-01-01 09:00:00"})
        req = self.q("SELECT * FROM booking_requests WHERE id = ?", (rid,))
        with mock.patch("smtplib.SMTP", FakeSMTP), mock.patch.dict(os.environ, MAIL_ENV):
            r = c.post(f"/staff/requests/{req['id']}", data={
                "action": "confirm", "patient_id": "", "branch_id": self.malolos, "service_id": self.svc,
                "dentist_id": self.d1, "date": monday.isoformat(), "time": "11:00"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(len(SENT), 1)
        self.assertEqual(SENT[0]["To"], "dentist.malolos" + DOMAIN)

    def test_opt_out_failure_and_demo(self):
        c = self.login("reception.malolos")
        day = self.next_weekday(1, weeks=10)
        self.conn.execute("UPDATE users SET notify_email = 0 WHERE id = ?", (self.d1,))
        with mock.patch("smtplib.SMTP", FakeSMTP), mock.patch.dict(os.environ, MAIL_ENV):
            c.post("/staff/appointments/new", data=self._form(day, "09:00", self.d1))
            self.conn.execute("UPDATE users SET notify_email = 1 WHERE id = ?", (self.d1,))
            FakeSMTP.fail = True
            r = c.post("/staff/appointments/new", data=self._form(day, "11:00", self.d1))
            self.assertEqual(r.status_code, 302)  # booking still saved
        a1 = self.q("SELECT id FROM appointments WHERE dentist_id = ? AND start_at = ?", (self.d1, f"{day} 09:00"))
        a2 = self.q("SELECT id FROM appointments WHERE dentist_id = ? AND start_at = ?", (self.d1, f"{day} 11:00"))
        self.assertEqual(self._emails(a1["id"])[0]["status"], "skipped")
        e = self._emails(a2["id"])[0]
        self.assertEqual(e["status"], "failed")
        self.assertIn("OSError", e["error"])
        self.assertEqual(SENT, [])
        # demo mode never sends, even with credentials
        self.app.config["APP_ENV"] = "demo"
        try:
            with mock.patch("smtplib.SMTP", FakeSMTP), mock.patch.dict(os.environ, MAIL_ENV):
                c.post("/staff/appointments/new", data=self._form(day, "14:00", self.d1))
        finally:
            self.app.config["APP_ENV"] = "development"
        a3 = self.q("SELECT id FROM appointments WHERE dentist_id = ? AND start_at = ?", (self.d1, f"{day} 14:00"))
        self.assertEqual(self._emails(a3["id"])[0]["status"], "demo")
        self.assertEqual(SENT, [])

    def test_user_toggle_and_system_page(self):
        c = self.login("admin")
        page = c.get(f"/staff/admin/users/{self.d1}")
        self.assertIn(b"Email this dentist about their appointments", page.data)
        with mock.patch.dict(os.environ, {"MAIL_USERNAME": "", "MAIL_PASSWORD": ""}):
            self.assertIn(b"Not set up", c.get("/staff/admin/system").data)
        with mock.patch("smtplib.SMTP", FakeSMTP), mock.patch.dict(os.environ, MAIL_ENV):
            self.assertIn(b"Send me a test email", c.get("/staff/admin/system").data)
            r = c.post("/staff/admin/system/test-email", follow_redirects=True)
            self.assertIn(b"Test email sent", r.data)
        self.assertEqual(SENT[0]["To"], "admin" + DOMAIN)
        self.assertEqual(self.login("staff.malolos").post("/staff/admin/system/test-email").status_code, 403)

    def test_branch_sender_and_fallback(self):
        c = self.login("reception.malolos")
        day = self.next_weekday(2, weeks=11)
        env = {"MAIL_USERNAME": "", "MAIL_PASSWORD": "", "MAIL_MALOLOS_USERNAME": "malolos.branch@example.test",
               "MAIL_MALOLOS_PASSWORD": "abcd efgh ijkl mnop"}
        with mock.patch("smtplib.SMTP", FakeSMTP), mock.patch.dict(os.environ, env):
            c.post("/staff/appointments/new", data=self._form(day, "09:00", self.d1))
            self.assertEqual(FakeSMTP.last_login, "malolos.branch@example.test")
            self.assertIn("malolos.branch@example.test", SENT[0]["From"])
            self.assertIn("Dental Haven Malolos", SENT[0]["From"])
            page = self.login("admin").get("/staff/admin/system").data
            self.assertIn(b"malolos.branch@example.test", page)
            self.assertIn(b"MAIL_BOCAUE_USERNAME", page)  # other branches show as not set up
            # a Guiguinto appointment has no sender (no branch account, no default) → not sent
            g_branch = self.branch("guiguinto")
            friday = self.next_weekday(4, weeks=11)
            self.login("admin").post("/staff/appointments/new", data=dict(self._form(friday, "09:00", self.d1), branch_id=g_branch))
        a = self.q("SELECT id FROM appointments WHERE dentist_id = ? AND start_at = ?", (self.d1, f"{friday} 09:00"))
        self.assertEqual(self._emails(a["id"])[0]["status"], "not_set_up")
        self.assertEqual(len(SENT), 1)
