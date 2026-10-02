"""Website sections: edit headings, texts, labels and photos per section, show/hide, back to default."""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00"
       b"\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82")


class TestWebsiteSections(Base):
    def setUp(self):
        super().setUp()
        self.conn.execute("DELETE FROM site_text")

    def form(self, section, **values):
        from app.site_sections import SECTION_BY_ID, load, value
        saved = load(self.conn)
        data = {"section": section}
        for key, _l, _d, kind in SECTION_BY_ID[section]["fields"]:
            if kind == "show":
                if value(saved, key) != "0":
                    data[key] = "1"
            else:
                data[key] = value(saved, key)
        for k, v in values.items():
            k = k.replace("__", ".")
            if v is None:
                data.pop(k, None)
            else:
                data[k] = v
        return data

    def test_edit_texts_labels_and_reset(self):
        admin = self.login("admin")
        page = admin.get("/staff/admin/website").data.decode()
        self.assertIn("Main services", page)
        self.assertIn("Everything your smile needs, *under one roof*", page)
        # defaults show on the site unchanged
        home = self.app.test_client().get("/").data.decode()
        self.assertIn("Everything your smile needs, <em>under one roof</em>", home)
        # edit a heading (with the accent), an intro and a button label
        admin.post("/staff/admin/website", data=self.form("services", services__title="All your dental care, *one clinic*",
                                                          services__intro="Simple <b>intro</b>", services__card_btn="Reserve"))
        home = self.app.test_client().get("/").data.decode()
        self.assertIn("All your dental care, <em>one clinic</em>", home)
        self.assertIn("Simple &lt;b&gt;intro&lt;/b&gt;", home)
        self.assertIn("Reserve <span aria-hidden=\"true\">→</span>", home)
        self.assertNotIn("under one roof", home)
        # only changed texts are stored
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM site_text"), 3)
        page = admin.get("/staff/admin/website").data.decode()
        self.assertIn("Edited", page)
        self.assertIn("Original: Everything your smile needs, *under one roof*", page)
        # emptying a box goes back to the original
        admin.post("/staff/admin/website", data=self.form("services", services__title=""))
        self.assertIsNone(self.q("SELECT key FROM site_text WHERE key = 'services.title'"))
        self.assertIn("under one roof", self.app.test_client().get("/").data.decode())
        # menu and footer labels on every page
        admin.post("/staff/admin/website", data=self.form("header", nav__book="Book an appointment"))
        admin.post("/staff/admin/website", data=self.form("footer", footer__fine="© 2026 Dental Haven Dental Clinic"))
        page = self.app.test_client().get("/inquire").data.decode()
        self.assertIn("Book an appointment", page)
        self.assertIn("© 2026 Dental Haven Dental Clinic", page)
        # the headline is the same text as Website content → home_hero
        admin.post("/staff/admin/website", data=self.form("hero", **{"@home_hero.title": "Smiles for the whole *family*"}))
        self.assertEqual(self.q("SELECT title FROM site_content WHERE key = 'home_hero'")["title"], "Smiles for the whole *family*")
        self.assertIn("Smiles for the whole <em>family</em>", self.app.test_client().get("/").data.decode())
        self.conn.execute("UPDATE site_content SET title = '' WHERE key = 'home_hero'")
        # audit trail
        self.assertTrue(self.q("SELECT id FROM audit_log WHERE action = 'site_text_updated'"))

    def test_hide_section_and_menu_link(self):
        admin = self.login("admin")
        home = self.app.test_client().get("/").data.decode()
        self.assertIn('id="clinic"', home)
        self.assertIn('id="specialty"', home)
        admin.post("/staff/admin/website", data=self.form("why", why__show=None))
        admin.post("/staff/admin/website", data=self.form("specialty", specialty__show=None))
        home = self.app.test_client().get("/").data.decode()
        self.assertNotIn('id="clinic"', home)
        self.assertNotIn('id="specialty"', home)
        self.assertNotIn("#specialty", home)  # menu link and hero button are hidden too
        admin.post("/staff/admin/website", data=self.form("why", why__show="1"))
        self.assertIn('id="clinic"', self.app.test_client().get("/").data.decode())
        self.conn.execute("DELETE FROM site_text")

    def test_photo_upload_from_a_section_and_access(self):
        admin = self.login("admin")
        r = admin.post("/staff/admin/content/photos", data={"key": "lab", "next": "/staff/admin/website#s-lab",
                                                            "image": (io.BytesIO(PNG), "lab.png")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/staff/admin/website#s-lab"))
        self.assertTrue(self.q("SELECT image_path FROM site_images WHERE key = 'lab'"))
        # outside redirects are ignored
        r = admin.post("/staff/admin/content/photos", data={"key": "lab", "action": "remove", "next": "https://evil.example/"})
        self.assertIn("/staff/admin/content", r.headers["Location"])
        # unknown section is refused; staff without content access can't open the editor
        self.assertEqual(admin.post("/staff/admin/website", data={"section": "nope"}).status_code, 400)
        self.assertEqual(self.login("reception.malolos").get("/staff/admin/website").status_code, 403)
