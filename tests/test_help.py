import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_app import Base  # noqa: E402


class TestHelp(Base):
    def test_every_guide_opens_and_search_finds_it(self):
        from app.help import ARTICLES, CATEGORIES
        from app.permissions import PERM_KEYS
        slugs = [a["slug"] for a in ARTICLES]
        self.assertEqual(len(slugs), len(set(slugs)))
        for a in ARTICLES:
            self.assertIn(a["cat"], CATEGORIES)
            for p in a["perms"] or []:
                self.assertIn(p, PERM_KEYS, a["slug"])
        c = self.login("admin")
        for s in slugs:
            r = c.get(f"/staff/help/{s}")
            self.assertEqual(r.status_code, 200, s)
        page = c.get("/staff/help/?q=how to add bill").data.decode()
        self.assertIn("Create a bill", page)
        self.assertIn("Send a case to the lab", c.get("/staff/help/?q=lab").data.decode())
        self.assertIn("Register a new patient", c.get("/staff/help/?q=new patient").data.decode())

    def test_guides_follow_the_users_role(self):
        d = self.login("dentist.malolos")
        page = d.get("/staff/help/").data.decode()
        self.assertIn("See my commissions", page)
        self.assertNotIn("Back up the data", page)
        self.assertEqual(d.get("/staff/help/backup").status_code, 404)
        self.assertNotIn("See my commissions", self.login("reception.malolos").get("/staff/help/").data.decode())


if __name__ == "__main__":
    unittest.main()
