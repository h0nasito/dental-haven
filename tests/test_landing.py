"""One-page landing: services, lab, portfolio (categories + before/after)."""
from __future__ import annotations

import io
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
        for name in ("General &amp; Preventive", "Cosmetic &amp; Restorative", "Prosthodontics", "Implants &amp; Surgery", "Orthodontics"):
            self.assertIn(name, html)
        for item in ("Composite veneers", "Zirconia restorations", "Clear aligners", "Extractions"):
            self.assertIn(item, html)
        self.assertIn("Digital Solutions Dental Laboratory", html)
        self.assertIn("CBCT", html)
        self.assertIn("Case photos coming soon", html)  # no published work yet
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
