"""Website chat assistant: info feed from site content, and the 'send to our team' form saved as a lead."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestChat(Base):
    def _client_with_csrf(self):
        c = self.app.test_client()
        html = c.get("/").data.decode()
        token = re.search(r'data-csrf="([^"]+)"', html).group(1)
        return c, token, html

    def test_widget_and_info(self):
        c, _, html = self._client_with_csrf()
        self.assertIn('id="dh-chat"', html)
        self.assertIn("js/chat.js", html)
        self.assertIn('data-lang="tl"', html)
        d = c.get("/chat/info.json").get_json()
        names = [b["name"] for b in d["branches"]]
        self.assertEqual(names[:4], ["Malolos", "Guiguinto", "Bocaue", "San Jose del Monte"])
        malolos = d["branches"][0]
        self.assertIn("+63 927 277 7833", malolos["phones"])
        self.assertTrue(malolos["hours"])
        self.assertTrue(malolos["hours"] == ["Monday – Saturday: 9:00 AM – 6:00 PM", "Sunday: Closed"])
        self.assertEqual(len(d["services"]), 8)
        self.assertEqual(d["prices"], [])  # live site: no prices until the clinic confirms its real price list
        raw = c.get("/chat/info.json").data.decode()
        for pt in self.conn.all("SELECT first_name, last_name, phone FROM patients LIMIT 20"):  # no patient data, ever
            self.assertNotIn(f"{pt['first_name']} {pt['last_name']}", raw)

    def test_send_to_team_creates_chat_lead(self):
        c, token, _ = self._client_with_csrf()
        # no CSRF → refused
        self.assertEqual(c.post("/chat/message", data={"full_name": "X"}).status_code, 400)
        r = c.post("/chat/message", headers={"X-CSRF-Token": token}, data={"full_name": "Chat Demo", "phone": "0917 555 0101",
                                                                         "message": "Do you do veneers on Sundays?"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("consent_privacy", r.get_json()["errors"])
        branch = self.branch("bocaue")
        r = c.post("/chat/message", headers={"X-CSRF-Token": token}, data={
            "full_name": "Chat Demo", "phone": "0917 555 0101", "branch_id": branch, "message": "Do you do veneers on Sundays?",
            "consent_privacy": "1"})
        self.assertTrue(r.get_json()["ok"])
        lead = self.q("SELECT * FROM leads WHERE full_name = 'Chat Demo'")
        self.assertEqual((lead["source"], lead["branch_id"], lead["status"]), ("chat", branch, "new"))
        # honeypot: silently ignored
        c.post("/chat/message", headers={"X-CSRF-Token": token}, data={"full_name": "Bot", "phone": "0917 555 0102", "message": "spam",
                                                                     "consent_privacy": "1", "website": "http://spam"})
        self.assertIsNone(self.q("SELECT id FROM leads WHERE full_name = 'Bot'"))
        page = self.login("admin").get("/staff/leads?source=chat").data
        self.assertIn(b"Chat Demo", page)
        self.assertIn(b"Website chat", page)


class TestChatKnowledge(Base):
    def test_procedures_complete_and_served(self):
        from app.chat_procedures import PROCEDURES
        slugs = {r["slug"] for r in self.conn.all("SELECT slug FROM services")}
        keys = set()
        for p in PROCEDURES:
            self.assertNotIn(p["key"], keys)
            keys.add(p["key"])
            self.assertIn(p["service"], slugs, p["key"])
            self.assertTrue(p["kw"], p["key"])
            for aspect in ("what", "duration", "pain", "recovery", "lasts"):
                if p[aspect] is not None:
                    self.assertTrue(p[aspect]["en"] and p[aspect]["tl"], (p["key"], aspect))
            self.assertIsNotNone(p["duration"], p["key"])  # every procedure can answer "how long?"
        for k in ("extraction", "wisdom", "root_canal", "braces", "implant", "crown", "filling", "cleaning", "deep_cleaning", "whitening"):
            self.assertIn(k, keys)
        info = self.app.test_client().get("/chat/info.json").get_json()
        self.assertEqual(len(info["procedures"]), len(PROCEDURES))
        ext = next(p for p in info["procedures"] if p["key"] == "extraction")
        self.assertIn("minutes", ext["duration"]["en"])
