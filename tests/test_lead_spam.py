"""Website spam: set aside in Leads > Spam (not counted as new), restorable, deletable; Philippine phone format."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402

SPAM = ("Hey\n\nInclude dentalhaven.net in Google's Search Index so it can appear in online search results!\n\n"
        "Submit dentalhaven.net today: domainsubmit.site")


class TestLeadSpam(Base):
    def post_inquiry(self, **kw):
        c = self.app.test_client()
        page = c.get("/inquire").data.decode()
        import re
        token = re.search(r'name="csrf_token" value="([^"]+)"', page)
        data = {"full_name": "Test Person", "phone": "0917 123 4567", "email": "", "message": "How much is cleaning?",
                "consent_privacy": "1", "started": str(int(time.time()) - 30)}
        if token:
            data["csrf_token"] = token.group(1)
        data.update(kw)
        return c.post("/inquire", data=data, headers={"X-Forwarded-For": f"10.9.{len(kw)}.{int(time.time() * 1000) % 250}"})

    def test_spam_is_set_aside(self):
        r = self.post_inquiry(full_name="Domains QT", phone="", email="domains@search-dentalhaven.net", message=SPAM)
        self.assertEqual(r.status_code, 302)                       # same thank-you as everyone
        lead = self.q("SELECT * FROM leads WHERE full_name = 'Domains QT'")
        self.assertEqual(lead["spam"], 1)
        self.assertIn("pretends to be from Dental Haven", lead["spam_reason"])
        r = self.post_inquiry(full_name="Real Patient QT", message="Hi po, magkano ang braces? Salamat")
        self.assertEqual(self.q("SELECT spam FROM leads WHERE full_name = 'Real Patient QT'")["spam"], 0)
        c = self.login("admin")
        self.assertNotIn("Domains QT", c.get("/staff/leads?status=open").data.decode())
        self.assertIn("Domains QT", c.get("/staff/leads?status=spam").data.decode())
        # not spam -> back in the inbox; mark as spam again; delete
        c.post(f"/staff/leads/{lead['id']}", data={"action": "not_spam"})
        self.assertEqual(self.q("SELECT spam FROM leads WHERE id = ?", (lead["id"],))["spam"], 0)
        c.post(f"/staff/leads/{lead['id']}", data={"action": "spam"})
        self.assertEqual(self.q("SELECT spam FROM leads WHERE id = ?", (lead["id"],))["spam"], 1)
        c.post(f"/staff/leads/{lead['id']}", data={"action": "delete_spam"})
        self.assertIsNone(self.q("SELECT id FROM leads WHERE id = ?", (lead["id"],)))
        # a real lead can't be deleted that way
        real = self.q("SELECT id FROM leads WHERE full_name = 'Real Patient QT'")["id"]
        self.assertEqual(c.post(f"/staff/leads/{real}", data={"action": "delete_spam"}).status_code, 400)

    def test_phone_must_look_real(self):
        r = self.post_inquiry(full_name="Bad Phone QT", phone="47539940")
        self.assertEqual(r.status_code, 200)
        self.assertIn("0917 123 4567", r.data.decode())
        self.assertIsNone(self.q("SELECT id FROM leads WHERE full_name = 'Bad Phone QT'"))
        self.post_inquiry(full_name="Abroad QT", phone="+971 50 123 4567")
        self.assertIsNotNone(self.q("SELECT id FROM leads WHERE full_name = 'Abroad QT'"))
