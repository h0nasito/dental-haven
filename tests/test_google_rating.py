"""Google rating per branch on the website."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestGoogleRating(Base):
    """Google rating per branch, entered by staff and shown on the website (no Google account connected)."""

    def test_rating_on_website(self):
        home = self.app.test_client().get("/").data.decode()
        self.assertNotIn("Rated on Google", home)
        a = self.login("admin")
        bid = self.branch("malolos")
        b = self.q("SELECT * FROM branches WHERE id = ?", (bid,))
        form = {k: b[k] or "" for k in ("name", "address", "phone", "email", "map_url", "facebook_url", "waze_url", "hours_text", "intro")}
        r = a.post(f"/staff/admin/branches/{bid}", data={**form, "section": "details", "google_rating": "6",
                                                         "google_review_count": "220"})
        self.assertIsNone(self.q("SELECT google_rating FROM branches WHERE id = ?", (bid,))["google_rating"])
        a.post(f"/staff/admin/branches/{bid}", data={**form, "section": "details", "google_rating": "5.0",
                                                     "google_review_count": "220", "google_reviews_url": "https://maps.app.goo.gl/example"})
        a.post(f"/staff/admin/branches/{self.branch('sjdm')}", data={**{k: (self.q("SELECT * FROM branches WHERE id = ?", (self.branch('sjdm'),))[k] or "") for k in form},
                                                                     "section": "details", "google_rating": "4.7", "google_review_count": "12"})
        row = self.q("SELECT google_rating, google_review_count, google_rating_as_of FROM branches WHERE id = ?", (bid,))
        self.assertEqual((row["google_rating"], row["google_review_count"]), (5.0, 220))
        self.assertTrue(row["google_rating_as_of"])
        home = self.app.test_client().get("/").data.decode()
        self.assertIn("Rated on Google", home)
        self.assertIn("232 Google reviews across 2 branches", home)
        self.assertIn(">5.0<", home)  # (5.0*220 + 4.7*12) / 232 = 4.98
        self.assertIn("https://maps.app.goo.gl/example", home)
        self.assertIn("Rated on Google", self.app.test_client().get("/feedback").data.decode())
