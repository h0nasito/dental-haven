"""Patient guides, clinic hours on the website, and chat links to guides."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestGuides(Base):
    def test_starter_guides_and_pages(self):
        c = self.app.test_client()
        slugs = {r["slug"] for r in self.conn.all("SELECT slug FROM guides WHERE published = 1")}
        for s in ("childs-first-dental-visit", "preventive-dentistry-for-kids", "silver-diamine-fluoride", "about-dental-fillings",
                  "white-spots-and-fluorosis", "veneers-vs-crowns"):
            self.assertIn(s, slugs)
        page = c.get("/guides/veneers-vs-crowns").data.decode()
        self.assertIn("Veneers vs. crowns", page)
        self.assertIn("<h2>Crowns</h2>", page)
        self.assertIn("Book a consultation", page)
        self.assertIn("a diagnosis", page)
        self.assertIn("<li>Cracked or broken teeth</li>", page)  # list after an intro line
        self.assertIn("More patient guides", page)
        self.assertEqual(c.get("/guides/nope").status_code, 404)
        self.assertIn("Your child&#39;s first dental visit", c.get("/guides").data.decode())
        ped = c.get("/services/pediatric-dentistry").data.decode()
        for t in ("first dental visit", "cleanings, fluoride and sealants", "Silver diamine fluoride"):
            self.assertIn(t, ped)
        home = c.get("/").data.decode()
        self.assertIn('id="guides"', home)
        self.assertEqual(home.count('class="guide-card"'), 6)  # one per service
        self.assertIn("Your child&#39;s first dental visit", home)
        info = c.get("/chat/info.json").get_json()
        self.assertTrue(any(g["slug"] == "silver-diamine-fluoride" and g["service"] == "pediatric-dentistry" for g in info["guides"]))

    def test_hours_shown(self):
        home = self.app.test_client().get("/").data.decode()
        self.assertIn("Monday – Saturday: 9:00 AM – 6:00 PM", home)
        self.assertIn("All branches:", home)
        self.assertIn("Sunday: Closed", self.app.test_client().get("/branches/bocaue").data.decode())

    def test_admin_edit_hide_and_seed_keeps_edits(self):
        from app.seed import seed_base
        c = self.login("admin")
        gd = self.q("SELECT * FROM guides WHERE slug = 'about-dental-fillings'")
        page = c.get("/staff/admin/content").data.decode()
        self.assertIn("Patient guides", page)
        r = c.post(f"/staff/admin/content/guides/{gd['id']}", data={
            "title": "Fillings, explained", "slug": gd["slug"], "service_id": gd["service_id"], "summary": "Edited summary.",
            "body": gd["body"], "sort_order": 0})  # 'published' unticked → hidden
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.app.test_client().get("/guides/about-dental-fillings").status_code, 404)
        seed_base(self.conn)  # runs on every start: must not overwrite or re-publish
        row = self.q("SELECT * FROM guides WHERE slug = 'about-dental-fillings'")
        self.assertEqual((row["title"], row["published"]), ("Fillings, explained", 0))
        # new guide, slug from title, duplicate slug refused
        r = c.post("/staff/admin/content/guides/new", data={"title": "Teeth whitening FAQ", "service_id": "", "summary": "s",
                                                          "body": "Whitening basics for patients. " * 3, "published": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.app.test_client().get("/guides/teeth-whitening-faq").status_code, 200)
        r = c.post("/staff/admin/content/guides/new", data={"title": "Teeth whitening FAQ", "body": "x" * 40})
        self.assertIn(b"already uses this URL name", r.data)
        self.assertEqual(self.login("reception.malolos").get("/staff/admin/content/guides/new").status_code, 403)
        self.conn.execute("UPDATE guides SET published = 1, title = ?, summary = ? WHERE slug = 'about-dental-fillings'", (gd["title"], gd["summary"]))
        self.conn.execute("DELETE FROM guides WHERE slug = 'teeth-whitening-faq'")
