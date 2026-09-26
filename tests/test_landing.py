"""One-page landing: services, lab, portfolio (categories + before/after)."""
from __future__ import annotations

import io
import os
from unittest import mock
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


def tiny_png():
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"\x00\xff\xff\xff"
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class TestLanding(Base):
    def test_sections_services_and_lab(self):
        self.conn.execute("UPDATE gallery_items SET published = 0")
        html = self.app.test_client().get("/").data.decode()
        for anchor in ('id="work"', 'id="services"', 'id="lab"', 'id="branches"'):
            self.assertIn(anchor, html)
        for name in ("General &amp; Preventive", "Cosmetic &amp; Restorative", "Prosthodontics", "Implants &amp; Surgery", "Orthodontics &amp; TMJ", "Pediatrics &amp; Special Care Dentistry"):
            self.assertIn(name, html)
        for item in ("Composite veneers", "Zirconia restorations", "Clear aligners", "Extractions", "Management of TMJ disorders",
                     "Preventive and corrective dentistry", "Crowns for kids", "Conscious sedation"):
            self.assertIn(item, html)
        self.assertIn("Digital Solutions Dental Laboratory", html)
        self.assertIn("CBCT", html)
        # no published work yet: stock sample photos, clearly labelled, and no "real results" claim
        self.assertIn("Sample photos.", html)
        self.assertIn("images.unsplash.com", html)
        self.assertNotIn("Real results", html)
        self.assertIn("https://images.unsplash.com", self.app.test_client().get("/").headers["Content-Security-Policy"])
        with mock.patch.dict(os.environ, {"STOCK_PHOTOS": "off"}):
            off = self.app.test_client().get("/").data.decode()
        self.assertNotIn("images.unsplash.com", off)
        self.assertIn("Case photos coming soon", off)
        self.assertNotIn("Patient feedback will be shared", html)  # empty feedback section is hidden

    def test_portfolio_before_after_and_filters(self):
        c = self.login("admin")
        r = c.post("/staff/admin/content/gallery", content_type="multipart/form-data", data={
            "action": "add", "title": "Veneer case", "caption": "", "category": "cosmetic", "authorization_note": "consent #1",
            "authorized": "1", "image": (io.BytesIO(tiny_png()), "after.png"), "before_image": (io.BytesIO(tiny_png()), "before.png")})
        self.assertEqual(r.status_code, 302)
        g = self.q("SELECT * FROM gallery_items WHERE title = 'Veneer case'")
        self.assertEqual(g["category"], "cosmetic")
        self.assertTrue(g["before_image_path"])
        self.assertNotIn("Veneer case", self.app.test_client().get("/").data.decode())  # unpublished
        c.post("/staff/admin/content/gallery", data={"action": "toggle", "id": g["id"]})
        html = self.app.test_client().get("/").data.decode()
        self.assertIn("Veneer case", html)
        self.assertIn('class="ba-range"', html)
        self.assertIn("Cosmetic &amp; Restorative", html)
        self.assertNotIn("Case photos coming soon", html)

    def test_reviews_section(self):
        self.conn.execute("UPDATE testimonials SET published = 0")
        html = self.app.test_client().get("/").data.decode()
        self.assertIn('id="reviews"', html)
        self.assertIn("facebook.com/dentalhavenmalolos/reviews", html)  # links to real reviews, nothing invented
        self.assertNotIn('class="lp-stars"', html)
        c = self.login("admin")
        c.post("/staff/admin/content/testimonials", data={
            "action": "add", "quote": "Synthetic review for testing.", "attribution": "Test P.", "consent_note": "test consent",
            "rating": "5", "source": "Facebook review", "branch_id": str(self.branch("bocaue"))})
        t = self.q("SELECT * FROM testimonials WHERE quote = 'Synthetic review for testing.'")
        self.assertEqual((t["rating"], t["source"]), (5, "Facebook review"))
        c.post("/staff/admin/content/testimonials", data={"action": "toggle", "id": t["id"]})  # not approved yet → refused
        self.assertNotIn("Synthetic review", self.app.test_client().get("/").data.decode())
        c.post("/staff/admin/content/testimonials", data={"action": "approve", "id": t["id"]})
        c.post("/staff/admin/content/testimonials", data={"action": "toggle", "id": t["id"]})
        html = self.app.test_client().get("/").data.decode()
        self.assertIn("Synthetic review for testing.", html)
        self.assertIn('aria-label="5 out of 5 stars"', html)
        self.assertIn("Bocaue · Facebook review", html)

    def test_featured_before_after(self):
        c = self.login("admin")
        html = self.app.test_client().get("/").data.decode()
        self.assertIn('id="specialty"', html)
        if 'lp-aes-main' not in html:
            self.assertIn("Before &amp; after photos of our aesthetic cases are coming soon", html)
        c.post("/staff/admin/content/gallery", content_type="multipart/form-data", data={
            "action": "add", "title": "Smile makeover case", "category": "cosmetic", "authorization_note": "consent #9", "authorized": "1",
            "image": (io.BytesIO(tiny_png()), "after.png"), "before_image": (io.BytesIO(tiny_png()), "before.png")})
        g = self.q("SELECT * FROM gallery_items WHERE title = 'Smile makeover case'")
        c.post("/staff/admin/content/gallery", data={"action": "feature", "id": g["id"]})  # unpublished → refused
        self.assertEqual(self.q("SELECT featured FROM gallery_items WHERE id = ?", (g["id"],))["featured"], 0)
        c.post("/staff/admin/content/gallery", data={"action": "toggle", "id": g["id"]})
        c.post("/staff/admin/content/gallery", data={"action": "feature", "id": g["id"]})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM gallery_items WHERE featured = 1")["n"], 1)
        html = self.app.test_client().get("/").data.decode()
        self.assertIn('class="lp-hero-ba"', html)
        self.assertIn('class="lp-aes-main"', html)
        self.assertIn("Compare before and after: Smile makeover case", html)

    def test_website_photos(self):
        c = self.login("admin")
        r = c.post("/staff/admin/content/photos", content_type="multipart/form-data",
                   data={"key": "hero", "image": (io.BytesIO(tiny_png()), "hero.png")})
        self.assertEqual(r.status_code, 302)
        svc = self.q("SELECT * FROM services WHERE slug = 'aesthetic-dentistry'")
        form = {k: str(svc[k]) for k in ("name", "slug", "category", "summary", "body", "default_duration_min", "sort_order")}
        form.update({"active": "1", "bookable_online": "1", "image": (io.BytesIO(tiny_png()), "svc.png")})
        r = c.post(f"/staff/admin/services/{svc['id']}", data=form, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.q("SELECT image_path FROM services WHERE id = ?", (svc["id"],))["image_path"])
        html = self.app.test_client().get("/").data.decode()
        self.assertIn('lp-hero has-photo', html)
        self.assertIn('class="lp-svc-media"', html)
        self.assertEqual(self.login("staff.malolos").post("/staff/admin/content/photos", data={"key": "hero"}).status_code, 403)
