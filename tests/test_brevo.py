"""Sending through Brevo's web API (for hosts like DigitalOcean that block email ports)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class FakeResp:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestBrevo(Base):
    def setUp(self):
        super().setUp()
        self.env = mock.patch.dict(os.environ, {"BREVO_API_KEY": "xkeysib-test", "MAIL_MALOLOS_USERNAME": "malolos@mail.test",
                                                "MAIL_USERNAME": "main@mail.test"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_config_and_send_through_api(self):
        from app import dentist_mail
        with self.app.app_context():
            c = dentist_mail.config("malolos", "Malolos")
            self.assertEqual((c["transport"], c["sender"]), ("brevo", "malolos@mail.test"))
            self.assertEqual(dentist_mail.config("bocaue", "Bocaue")["sender"], "main@mail.test")  # falls back to the shared sender
            calls = []

            def fake_urlopen(req, timeout=0):
                calls.append(req)
                return FakeResp()
            with mock.patch("urllib.request.urlopen", fake_urlopen):
                dentist_mail.send_email("dentist@mail.test", "Subject", "Body", c)
            req = calls[0]
            self.assertEqual(req.full_url, "https://api.brevo.com/v3/smtp/email")
            self.assertEqual(req.get_header("Api-key"), "xkeysib-test")
            body = json.loads(req.data)
            self.assertEqual((body["sender"]["email"], body["to"][0]["email"], body["textContent"]), ("malolos@mail.test", "dentist@mail.test", "Body"))

    def test_patient_email_daily_limit_counts_all_senders(self):
        from app import patient_mail
        from app.util import now_str
        self.conn.execute("DELETE FROM email_outbox")
        self.conn.execute("DELETE FROM settings WHERE key = 'mail.daily_limit'")
        pid = self.q("SELECT id FROM patients LIMIT 1")["id"]
        for i in range(5):
            self.conn.execute("INSERT INTO email_outbox (kind, patient_id, to_email, subject, body, dedupe_key, created_at) "
                              "VALUES ('announcement', ?, 'x@mail.test', 's', 'b', ?, ?)", (pid, f"brevo-{i}", now_str()))
        self.conn.execute("UPDATE patients SET active = 1, opt_out_all = 0, news_opt_out = 0 WHERE id = ?", (pid,))
        sent = []
        with self.app.test_request_context():
            self.assertEqual(patient_mail.daily_limit(self.conn), 280)
            from app import settings
            settings.put("mail.daily_limit", 3, None, self.conn)
            self.app.config["APP_ENV"] = "production"
            try:
                n = patient_mail.send_queued(self.conn, sender_fn=lambda c, to, s, b, u="": sent.append(c["sender"]))
            finally:
                self.app.config["APP_ENV"] = "development"
        self.assertEqual(n, 3)  # the limit is for the whole Brevo account, not per branch sender
        self.conn.execute("DELETE FROM email_outbox")
        self.conn.execute("DELETE FROM settings WHERE key = 'mail.daily_limit'")
