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


import io as _io  # noqa: E402
import json as _json  # noqa: E402
import os as _os  # noqa: E402
import urllib.error as _ue  # noqa: E402
from unittest import mock as _mock  # noqa: E402

FAKE = {"id": "ChIJTEST_place_id_12345", "rating": 4.8, "userRatingCount": 57, "googleMapsUri": "https://maps.google.com/?cid=1",
        "reviews": [{"rating": 5, "relativePublishTimeDescription": "a week ago", "publishTime": "2026-09-26T03:00:00Z",
                     "originalText": {"text": "Sample review text for the test."}, "googleMapsUri": "https://www.google.com/maps/reviews/x",
                     "authorAttribution": {"displayName": "Sample Reviewer", "uri": "https://www.google.com/maps/contrib/1",
                                           "photoUri": "https://lh3.googleusercontent.com/a/x"}},
                    {"rating": 4, "relativePublishTimeDescription": "2 months ago", "publishTime": "2026-08-01T03:00:00Z",
                     "text": {"text": "Second sample."}, "authorAttribution": {"displayName": "Another Sample", "photoUri": "http://bad"}}]}


class _Resp:
    def __init__(self, data):
        self.data = _json.dumps(data).encode()

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestGooglePlaces(Base):
    def setUp(self):
        super().setUp()
        self.calls = []
        _os.environ["GOOGLE_PLACES_API_KEY"] = "test-key-not-real"
        self.addCleanup(_os.environ.pop, "GOOGLE_PLACES_API_KEY", None)
        self.bid = self.branch("malolos")
        self.conn.execute("UPDATE branches SET google_place_id = 'ChIJTEST_place_id_12345', google_synced_at = NULL, google_sync_error = '' WHERE id = ?", (self.bid,))

    def opener(self, req, timeout=20):
        self.calls.append(req)
        return _Resp(FAKE)

    def test_sync_and_show(self):
        from app import google_places
        with self.app.app_context():
            from app.db import get_db
            self.assertEqual(google_places.run(get_db(), opener=self.opener), 1)
            self.assertEqual(google_places.run(get_db(), opener=self.opener), 0, "not again within 12 hours")
        req = self.calls[0]
        self.assertIn("places/ChIJTEST_place_id_12345", req.full_url)
        self.assertEqual(req.get_header("X-goog-fieldmask"), google_places.FIELDS)
        b = self.q("SELECT * FROM branches WHERE id = ?", (self.bid,))
        self.assertEqual((b["google_rating"], b["google_review_count"]), (4.8, 57))
        self.assertEqual(b["google_reviews_url"], "https://maps.google.com/?cid=1")
        rows = self.conn.all("SELECT * FROM google_reviews ORDER BY sort_order")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["author_photo"], "", "only https Google photos are kept")
        home = self.app.test_client().get("/").data.decode()
        self.assertIn("Sample review text for the test.", home)
        self.assertIn("Reviews from Google", home)
        self.assertIn("https://www.google.com/maps/contrib/1", home)
        self.assertIn("lh3.googleusercontent.com", self.app.test_client().get("/").headers["Content-Security-Policy"])

    def test_error_is_shown_to_admin(self):
        from app import google_places

        def failing(req, timeout=20):
            raise _ue.HTTPError(req.full_url, 403, "Forbidden", {}, _io.BytesIO(b'{"error": {"message": "API key not valid."}}'))
        with self.app.app_context():
            from app.db import get_db
            google_places.run(get_db(), opener=failing)
        b = self.q("SELECT * FROM branches WHERE id = ?", (self.bid,))
        self.assertIn("403", b["google_sync_error"])
        page = self.login("admin").get(f"/staff/admin/branches/{self.bid}").data.decode()
        self.assertIn("Not updating", page)
        self.assertIn("API key not valid.", page)

    def test_off_without_key(self):
        _os.environ.pop("GOOGLE_PLACES_API_KEY")
        from app import google_places
        with self.app.app_context():
            from app.db import get_db
            self.assertEqual(google_places.run(get_db(), opener=self.opener), 0)
        self.assertEqual(self.calls, [])

    def test_place_id_validation(self):
        a = self.login("admin")
        b = self.q("SELECT * FROM branches WHERE id = ?", (self.bid,))
        form = {k: b[k] or "" for k in ("name", "address", "phone", "email", "map_url", "facebook_url", "waze_url", "hours_text", "intro")}
        a.post(f"/staff/admin/branches/{self.bid}", data={**form, "section": "details", "google_place_id": "https://evil/../x"})
        self.assertEqual(self.q("SELECT google_place_id FROM branches WHERE id = ?", (self.bid,))["google_place_id"], "ChIJTEST_place_id_12345")
