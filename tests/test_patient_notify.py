"""Automatic patient messages (approved, declined, rescheduled, cancelled, reminders).
SMTP and SMS are faked: nothing is sent anywhere. All patients are synthetic."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402
from test_dentist_mail import MAIL_ENV, SENT, FakeSMTP  # noqa: E402

SMS = []


def fake_sms(number, message, cfg):
    SMS.append((number, message))


PATIENT_EMAIL = "juan.demo@example.test"


class TestPatientMessages(Base):
    def setUp(self):
        SENT.clear()
        SMS.clear()
        FakeSMTP.fail = False
        self.malolos = self.branch("malolos")
        self.d1 = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        self.svc = self.q("SELECT id FROM services WHERE slug='general-dentistry'")["id"]
        self.conn.execute("UPDATE users SET notify_email = 1")

    def _request(self, day, time, email=PATIENT_EMAIL, consent=0, ref="DH-TEST-PN"):
        rid = self.conn.insert("booking_requests", {
            "ref_code": ref, "full_name": "Juan Demo", "phone": "0917 000 1234", "email": email, "branch_id": self.malolos,
            "service_id": self.svc, "dentist_id": self.d1, "preferred_start": f"{day} {time}", "consent_privacy": 1,
            "consent_contact": consent, "status": "pending", "created_at": "2026-01-01 09:00:00"})
        return rid

    def _confirm(self, c, rid, day, time):
        return c.post(f"/staff/requests/{rid}", data={"action": "confirm", "patient_id": "", "branch_id": self.malolos,
                                                       "service_id": self.svc, "dentist_id": self.d1, "date": day.isoformat(), "time": time})

    def _to(self, addr):
        return [m for m in SENT if m["To"] == addr]

    def test_approve_reschedule_cancel_email_patient_and_dentist(self):
        c = self.login("reception.malolos")
        monday = self.next_weekday(0, weeks=12)
        rid = self._request(monday, "10:00")
        with mock.patch("smtplib.SMTP", FakeSMTP), mock.patch.dict(os.environ, MAIL_ENV):
            r = self._confirm(c, rid, monday, "10:00")
            appt = self.q("SELECT appointment_id FROM booking_requests WHERE id = ?", (rid,))["appointment_id"]
            flashed = c.get(r.headers["Location"]).data
            self.assertIn(b"The patient was notified by email", flashed)
            # patient: approved, with day/time/branch; dentist: new appointment
            pm = self._to(PATIENT_EMAIL)
            self.assertEqual(len(pm), 1)
            self.assertIn("confirmed", pm[0]["Subject"])
            body = pm[0].get_content()
            for part in ("approved", "Monday", "10:00 AM", "Malolos", "Preventive"):
                self.assertIn(part, body)
            self.assertEqual(len(self._to("dentist.malolos" + DOMAIN)), 1)
            # reschedule → patient told the new time
            c.post(f"/staff/appointments/{appt}/reschedule", data={"branch_id": self.malolos, "service_id": self.svc,
                                                                   "dentist_id": self.d1, "date": monday.isoformat(), "time": "14:00"})
            self.assertIn("moved", self._to(PATIENT_EMAIL)[-1]["Subject"])
            self.assertIn("2:00 PM", self._to(PATIENT_EMAIL)[-1].get_content())
            # cancel → patient AND dentist told; internal reason never emailed
            c.post(f"/staff/appointments/{appt}/status", data={"status": "cancelled", "reason": "Dentist sick"})
            self.assertIn("cancelled", self._to(PATIENT_EMAIL)[-1]["Subject"])
            self.assertIn("cancelled", self._to("dentist.malolos" + DOMAIN)[-1]["Subject"])
            for m in SENT:
                self.assertNotIn("Dentist sick", m.get_content())
        rows = self.conn.all("SELECT event, status, recipient_masked FROM patient_messages WHERE appointment_id = ? AND channel = 'email' ORDER BY id", (appt,))
        self.assertEqual([(r["event"], r["status"]) for r in rows], [("approved", "sent"), ("rescheduled", "sent"), ("cancelled", "sent")])
        self.assertEqual(rows[0]["recipient_masked"], "j***@example.test")  # full address never stored in the log
        page = c.get(f"/staff/appointments/{appt}").data
        self.assertIn(b"Messages to the patient", page)

    def test_decline_emails_patient_without_reason(self):
        c = self.login("reception.malolos")
        rid = self._request(self.next_weekday(1, weeks=12), "09:00", ref="DH-TEST-PN2")
        with mock.patch("smtplib.SMTP", FakeSMTP), mock.patch.dict(os.environ, MAIL_ENV):
            c.post(f"/staff/requests/{rid}", data={"action": "decline", "decline_reason": "Fully booked, internal note"})
        self.assertEqual(len(SENT), 1)
        self.assertEqual(SENT[0]["To"], PATIENT_EMAIL)
        self.assertNotIn("internal note", SENT[0].get_content())
        self.assertIn("another time", SENT[0].get_content())
        self.assertIn(b"Email to j***@example.test", c.get(f"/staff/requests/{rid}").data)

    def test_not_set_up_demo_and_sms(self):
        c = self.login("reception.malolos")
        rid = self._request(self.next_weekday(2, weeks=12), "09:00", ref="DH-TEST-PN3")
        with mock.patch("smtplib.SMTP", FakeSMTP), mock.patch.dict(os.environ, {"MAIL_USERNAME": "", "MAIL_PASSWORD": "", "SEMAPHORE_API_KEY": ""}):
            r = c.post(f"/staff/requests/{rid}", data={"action": "decline", "decline_reason": "x"}, follow_redirects=True)
        self.assertIn(b"NOT notified automatically", r.data)
        self.assertEqual(SENT, [])
        # SMS provider set → text goes to the normalised mobile number
        rid = self._request(self.next_weekday(3, weeks=12), "09:00", ref="DH-TEST-PN4")
        with mock.patch("app.patient_notify.send_sms", fake_sms), mock.patch.dict(os.environ, {"MAIL_USERNAME": "", "SEMAPHORE_API_KEY": "k"}):
            c.post(f"/staff/requests/{rid}", data={"action": "decline", "decline_reason": "x"})
        self.assertEqual(SMS[0][0], "09170001234")
        self.assertLessEqual(len(SMS[0][1]), 300)
        # demo never sends
        rid = self._request(self.next_weekday(4, weeks=12), "09:00", ref="DH-TEST-PN5")
        self.app.config["APP_ENV"] = "demo"
        try:
            with mock.patch("smtplib.SMTP", FakeSMTP), mock.patch("app.patient_notify.send_sms", fake_sms), \
                    mock.patch.dict(os.environ, dict(MAIL_ENV, SEMAPHORE_API_KEY="k")):
                c.post(f"/staff/requests/{rid}", data={"action": "decline", "decline_reason": "x"})
        finally:
            self.app.config["APP_ENV"] = "development"
        self.assertEqual(SENT, [])
        self.assertEqual(len(SMS), 1)
        self.assertEqual({r["status"] for r in self.conn.all("SELECT status FROM patient_messages WHERE booking_request_id = ?", (rid,))}, {"demo"})

    def test_reminders_follow_consent(self):
        from app import patient_notify
        c = self.login("reception.malolos")
        tuesday = self.next_weekday(1, weeks=13)
        yes = self._request(tuesday, "09:00", email="yes.demo@example.test", consent=1, ref="DH-TEST-R1")
        no = self._request(tuesday, "11:00", email="no.demo@example.test", consent=0, ref="DH-TEST-R2")
        self._confirm(c, yes, tuesday, "09:00")
        self._confirm(c, no, tuesday, "11:00")
        appts = [self.q("SELECT appointment_id FROM booking_requests WHERE id = ?", (i,))["appointment_id"] for i in (yes, no)]
        # make the reminders due now
        self.conn.execute(f"UPDATE reminders SET scheduled_for = '2000-01-01 00:00' WHERE appointment_id IN ({appts[0]}, {appts[1]})")
        SENT.clear()
        with self.app.test_request_context(), mock.patch("smtplib.SMTP", FakeSMTP), mock.patch.dict(os.environ, MAIL_ENV):
            n = patient_notify.send_due_reminders(self.conn)
            self.assertEqual(patient_notify.send_due_reminders(self.conn), 0)  # never sent twice
        self.assertEqual(n, 1)
        self.assertEqual([m["To"] for m in SENT], ["yes.demo@example.test"])
        self.assertIn("Reminder", SENT[0]["Subject"])
        r = self.q("SELECT status, result_note FROM reminders WHERE appointment_id = ?", (appts[0],))
        self.assertEqual((r["status"], r["result_note"]), ("sent_provider", "Sent automatically"))
        self.assertNotEqual(self.q("SELECT status FROM reminders WHERE appointment_id = ?", (appts[1],))["status"], "sent_provider")
