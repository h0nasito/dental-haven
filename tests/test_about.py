"""About us: team members and activities are added by staff and appear on the website only when published with consent."""
from __future__ import annotations

import io
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402
from test_patient_profile import PNG  # noqa: E402
import base64  # noqa: E402

IMG = base64.b64decode(PNG)


class TestAbout(Base):
    def test_hidden_until_added(self):
        home = self.app.test_client().get("/").data.decode()
        self.assertNotIn('id="about"', home)
        self.assertEqual(self.app.test_client().get("/about").status_code, 200)

    def test_team_member_needs_consent_to_publish(self):
        a = self.login("admin")
        data = {"name": "Dr. Sample Dentist", "title": "Head Dentist", "grp": "dentist", "bio": "Loves gentle care.",
                "branches": [str(self.branch("malolos"))], "published": "1", "consent_note": "", "action": "save"}
        r = a.post("/staff/admin/about/team/new", data=data)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(self.q("SELECT id FROM team_members"))
        a.post("/staff/admin/about/team/new", data={**data, "consent_note": "Agreed in writing",
                                                    "photo": (io.BytesIO(IMG), "me.png")}, content_type="multipart/form-data")
        m = self.q("SELECT * FROM team_members")
        self.assertEqual((m["published"], m["grp"]), (1, "dentist"))
        self.assertTrue(m["photo_path"])
        home = self.app.test_client().get("/").data.decode()
        self.assertIn('id="about"', home)
        self.assertIn("Dr. Sample Dentist", home)
        page = self.app.test_client().get("/about").data.decode()
        self.assertIn("Meet our dentists", page)
        self.assertIn("Loves gentle care.", page)
        self.assertIn("Malolos", page)
        # unpublish hides it
        a.post(f"/staff/admin/about/team/{m['id']}", data={**data, "published": "", "consent_note": "Agreed in writing"})
        self.assertNotIn("Dr. Sample Dentist", self.app.test_client().get("/about").data.decode())

    def test_activity_with_photos(self):
        a = self.login("admin")
        base = {"title": "School dental check-ups", "happened_on": (date.today() - timedelta(days=2)).isoformat(), "kind": "outreach",
                "body": "First paragraph.\n\nSecond paragraph.", "branch_id": "", "consent_note": "", "published": "1", "action": "save"}
        a.post("/staff/admin/about/activities/new", data={**base, "happened_on": (date.today() + timedelta(days=3)).isoformat()})
        self.assertIsNone(self.q("SELECT id FROM activities"))
        r = a.post("/staff/admin/about/activities/new", data={**base, "photos": [(io.BytesIO(IMG), "a.png"), (io.BytesIO(IMG), "b.png")]},
                   content_type="multipart/form-data")
        self.assertIsNone(self.q("SELECT id FROM activities"), "photos need a consent record before publishing")
        a.post("/staff/admin/about/activities/new", data={**base, "consent_note": "Parents signed photo consent",
                                                          "photos": [(io.BytesIO(IMG), "a.png"), (io.BytesIO(IMG), "b.png")]},
               content_type="multipart/form-data")
        act = self.q("SELECT * FROM activities")
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM activity_photos WHERE activity_id = ?", (act["id"],))["n"], 2)
        page = self.app.test_client().get(f"/about/activities/{act['id']}").data.decode()
        self.assertIn("Second paragraph.", page)
        self.assertIn("2 photos", self.app.test_client().get("/").data.decode())
        pid = self.q("SELECT id FROM activity_photos LIMIT 1")["id"]
        a.post(f"/staff/admin/about/activities/{act['id']}", data={"remove_photo": str(pid)})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM activity_photos")["n"], 1)
        a.post(f"/staff/admin/about/activities/{act['id']}", data={"action": "delete"})
        self.assertEqual(self.app.test_client().get(f"/about/activities/{act['id']}").status_code, 404)

    def test_only_content_managers(self):
        c = self.login("dentist.malolos")
        self.assertEqual(c.get("/staff/admin/about/").status_code, 403)
        self.assertEqual(self.login("admin").get("/staff/admin/about/").status_code, 200)

    def test_story_from_website_sections(self):
        self.conn.execute("INSERT INTO site_text (key, value) VALUES ('about.story', 'We started as one small clinic.')")
        self.assertIn("We started as one small clinic.", self.app.test_client().get("/").data.decode())
