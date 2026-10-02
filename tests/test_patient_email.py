"""Patient emails: birthday greetings, announcement / promotion blasts, consent, daily limits, unsubscribe."""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestPatientEmail(Base):
    def setUp(self):
        super().setUp()
        from app.util import now_str
        self.conn.execute("DELETE FROM email_outbox")
        self.conn.execute("DELETE FROM email_campaigns")
        self.conn.execute("DELETE FROM settings WHERE key LIKE 'birthday.%' OR key = 'mail.daily_limit'")
        # every other patient: no email, so only the synthetic ones below count
        self.conn.execute("UPDATE patients SET email = '' WHERE email NOT LIKE '%@mail.test'")
        ts = now_str()

        def pat(n, **kw):
            vals = {"first_name": f"pat{n}", "last_name": "Mailtest", "chart_no": f"MAIL-{n}", "email": f"p{n}@mail.test",
                    "active": 1, "consent_privacy": 1, "created_at": ts, "updated_at": ts, **kw}
            row = self.q("SELECT id FROM patients WHERE chart_no = ?", (vals["chart_no"],))
            if row:
                self.conn.update("patients", row["id"], vals)
                return row["id"]
            return self.conn.insert("patients", vals)
        self.p_promo = pat(1, consent_marketing=1, birth_date="1990-10-02")
        self.p_news = pat(2, consent_marketing=0, birth_date="1985-10-02")
        self.p_noconsent = pat(3, consent_privacy=0, consent_marketing=0, birth_date="1990-10-02")
        self.p_optout = pat(4, consent_marketing=1, opt_out_all=1, birth_date="1990-10-02")
        self.p_noemail = pat(5, email="", consent_marketing=1)
        self.p_deleted = pat(6, active=0, consent_marketing=1)
        self.p_leap = pat(7, birth_date="2000-02-29")
        self.p_newsout = pat(8, consent_marketing=1, news_opt_out=1)
        self.sent = []

    def fake_send(self, c, to, subject, body, unsubscribe=""):
        self.sent.append((to, subject, body, unsubscribe))

    def _with_sender(self):
        import os
        os.environ["MAIL_USERNAME"], os.environ["MAIL_PASSWORD"] = "clinic@mail.test", "app-pass"
        self.addCleanup(lambda: (os.environ.pop("MAIL_USERNAME", None), os.environ.pop("MAIL_PASSWORD", None)))

    def test_audiences(self):
        from app import patient_mail
        with self.app.app_context():
            ids = lambda kind: {r["id"] for r in self.conn.all(  # noqa: E731
                f"SELECT p.id FROM patients p WHERE {patient_mail.audience_sql(kind)[0]}")}
            self.assertEqual(ids("promotion") & {self.p_promo, self.p_news, self.p_noconsent, self.p_optout, self.p_noemail,
                                                 self.p_deleted, self.p_newsout}, {self.p_promo, self.p_newsout})
            self.assertEqual(ids("announcement") & {self.p_promo, self.p_news, self.p_noconsent, self.p_optout, self.p_noemail,
                                                    self.p_deleted, self.p_newsout}, {self.p_promo, self.p_news})

    def test_birthdays_once_a_day_with_promo_only_for_marketing(self):
        from app import patient_mail, settings
        with self.app.app_context():
            self.assertEqual(patient_mail.queue_birthdays(self.conn, date(2026, 10, 2)), 0)  # off by default
            settings.put("birthday.enabled", True, None, self.conn)
            settings.put("birthday.promo", "10% off cleaning this month.", None, self.conn)
            n = patient_mail.queue_birthdays(self.conn, date(2026, 10, 2))
            self.assertEqual(n, 2)  # p_promo + p_news; not the one without consent or opted out
            self.assertEqual(patient_mail.queue_birthdays(self.conn, date(2026, 10, 2)), 0)  # once a day
            rows = {r["patient_id"]: r for r in self.conn.all("SELECT * FROM email_outbox WHERE kind = 'birthday'")}
            self.assertIn("Happy birthday, Pat1", rows[self.p_promo]["subject"])
            self.assertIn("10% off cleaning", rows[self.p_promo]["body"])
            self.assertNotIn("10% off cleaning", rows[self.p_news]["body"])
            self.assertIn("/unsubscribe/", rows[self.p_news]["body"])
            # 29 February birthdays are greeted on 28 February in other years
            settings.put("birthday.last_run", "", None, self.conn)
            patient_mail.queue_birthdays(self.conn, date(2027, 2, 28))
            self.assertTrue(self.q("SELECT id FROM email_outbox WHERE patient_id = ? AND kind = 'birthday'", (self.p_leap,)))

    def test_campaign_flow_limits_and_unsubscribe(self):
        from app import patient_mail, settings
        self._with_sender()
        admin = self.login("admin")
        r = admin.post("/staff/admin/emails/new", data={"action": "save", "kind": "promotion", "subject": "October promo for {first_name}",
                                                        "body": "Hi {first_name},\n\nFree consultation this October."})
        cid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        page = admin.get(f"/staff/admin/emails/{cid}").data.decode()
        count = int(re.search(r'name="confirm_count" value="(\d+)"', page).group(1))
        self.assertEqual(count, 2)
        # a stale count is refused
        r = admin.post(f"/staff/admin/emails/{cid}", data={"action": "send", "kind": "promotion", "subject": "October promo for {first_name}",
                                                           "body": "Hi {first_name},\n\nFree consultation this October.", "confirm_count": "999"},
                       follow_redirects=True)
        self.assertIn("number of recipients changed", r.data.decode())
        r = admin.post(f"/staff/admin/emails/{cid}", data={"action": "send", "kind": "promotion", "subject": "October promo for {first_name}",
                                                           "body": "Hi {first_name},\n\nFree consultation this October.", "confirm_count": "2"},
                       follow_redirects=True)
        self.assertIn("Queued for 2 patient(s)", r.data.decode())
        self.assertEqual(self.q("SELECT status FROM email_campaigns WHERE id = ?", (cid,))["status"], "queued")
        # the patient unsubscribes before sending: their email is not sent
        with self.app.test_request_context():
            token = patient_mail.unsubscribe_token(self.p_newsout)
        c = self.app.test_client()
        page = c.get(f"/unsubscribe/{token}").data.decode()
        self.assertIn("Stop promotions only", page)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        r = c.post(f"/unsubscribe/{token}", data={"csrf_token": csrf, "choice": "promotions"})
        self.assertIn("You won", r.data.decode())
        self.assertEqual(self.q("SELECT consent_marketing FROM patients WHERE id = ?", (self.p_newsout,))["consent_marketing"], 0)
        self.assertEqual(c.get("/unsubscribe/not-a-real-token").status_code, 404)
        # sending respects the daily limit, then finishes
        with self.app.test_request_context():
            settings.put("mail.daily_limit", 20, None, self.conn)
            self.app.config["APP_ENV"] = "production"
            try:
                sent = patient_mail.send_queued(self.conn, sender_fn=self.fake_send)
            finally:
                self.app.config["APP_ENV"] = "development"
        self.assertEqual(sent, 1)
        self.assertEqual(self.sent[0][0], "p1@mail.test")
        self.assertEqual(self.sent[0][1], "October promo for Pat1")
        self.assertIn("/unsubscribe/", self.sent[0][3])
        self.assertEqual(self.q("SELECT status FROM email_campaigns WHERE id = ?", (cid,))["status"], "done")
        st = patient_mail.stats(self.conn, cid)
        self.assertEqual((st["sent"], st["cancelled"]), (1, 1))
        # the daily limit stops sending once reached
        with self.app.test_request_context():
            settings.put("mail.daily_limit", 1, None, self.conn)
            self.conn.execute("INSERT INTO email_outbox (kind, patient_id, to_email, subject, body, dedupe_key, created_at) "
                              "VALUES ('announcement', ?, 'p2@mail.test', 's', 'b', 'limit-test', '2026-01-01')", (self.p_news,))
            self.app.config["APP_ENV"] = "production"
            try:
                self.assertEqual(patient_mail.send_queued(self.conn, sender_fn=self.fake_send), 0)
            finally:
                self.app.config["APP_ENV"] = "development"

    def test_demo_never_sends_and_only_super_admin(self):
        from app import patient_mail
        self.conn.execute("INSERT INTO email_outbox (kind, patient_id, to_email, subject, body, dedupe_key, created_at) "
                          "VALUES ('announcement', ?, 'p2@mail.test', 's', 'b', 'demo-test', '2026-01-01')", (self.p_news,))
        self._with_sender()
        with self.app.test_request_context():
            self.app.config["APP_ENV"] = "demo"
            try:
                self.assertEqual(patient_mail.send_queued(self.conn, sender_fn=self.fake_send), 0)
            finally:
                self.app.config["APP_ENV"] = "development"
        self.assertEqual(self.sent, [])
        self.assertEqual(self.login("reception.malolos").get("/staff/admin/emails").status_code, 403)
        self.assertEqual(self.login("admin").get("/staff/admin/emails").status_code, 200)
