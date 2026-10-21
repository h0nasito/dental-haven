"""Dental chart: surfaces drawn on the right side of each tooth, coloured by the latest finding."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.views.chart import regions, tooth_views  # noqa: E402
from test_app import Base  # noqa: E402


class TestSurfaceLayout(unittest.TestCase):
    def test_regions(self):
        # patient's upper right: buccal on top, mesial towards the middle (your right)
        self.assertEqual(regions(16), {"top": "B", "bottom": "L", "left": "D", "right": "M", "center": "O"})
        self.assertEqual(regions(21), {"top": "B", "bottom": "L", "left": "M", "right": "D", "center": "O"})
        self.assertEqual(regions(36), {"top": "L", "bottom": "B", "left": "M", "right": "D", "center": "O"})
        self.assertEqual(regions(85), {"top": "L", "bottom": "B", "left": "D", "right": "M", "center": "O"})

    def test_colours_follow_history(self):
        e = lambda i, t, c, s, d: {"id": i, "tooth": t, "condition": c, "surfaces": s, "recorded_on": d}  # noqa: E731
        v = tooth_views([e(2, "36", "restoration", "O", "2026-10-02"), e(1, "36", "caries", "OB", "2026-10-01"),
                         e(3, "46", "missing", "", "2026-10-01"), e(4, "11", "crown", "", "2026-10-03")])
        self.assertEqual(v["36"]["surf"], {"O": "f-filled", "B": "f-caries"})
        self.assertEqual(v["36"]["tag"], "F")
        self.assertEqual((v["46"]["mark"], v["46"]["tag"]), ("x", "M"))
        self.assertEqual(v["11"]["whole"], "f-crown")
        v = tooth_views([e(5, "38", "impacted", "", "2026-10-01"), e(6, "48", "unerupted", "", "2026-10-01")])
        self.assertEqual((v["38"]["mark"], v["38"]["tag"], v["38"]["label"]), ("ring-solid", "Imp", "Impacted"))
        self.assertEqual((v["48"]["mark"], v["48"]["tag"], v["48"]["label"]), ("ring", "Un", "Unerupted"))


class TestChartPage(Base):
    def test_chart_draws_surfaces(self):
        pid = self.q("SELECT id FROM patients WHERE active = 1 ORDER BY id LIMIT 1")["id"]
        c = self.login("admin")
        c.post(f"/staff/patients/{pid}/chart", data={"tooth": "36", "condition": "caries", "surface_O": "1", "surface_D": "1"})
        page = c.get(f"/staff/patients/{pid}?tab=chart&tooth=36").data.decode()
        self.assertIn('id="tooth-preview"', page)
        self.assertIn("seg f-caries", page)
        for t in ("55", "18", "48", "75"):
            self.assertIn(f'<span class="ono">{t}</span>', page)


class TestChartPhotos(Base):
    def test_photo_with_chart_entry(self):
        import io
        from test_patient_photo import PNG
        pid = self.q("SELECT id FROM patients WHERE active = 1 ORDER BY id LIMIT 1")["id"]
        c = self.login("admin")
        r = c.post(f"/staff/patients/{pid}/chart", data={"tooth": "26", "condition": "caries", "surface_O": "1",
                                                          "photos": [(io.BytesIO(PNG), "tooth26.png")]}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        e = self.q("SELECT id FROM chart_entries WHERE patient_id = ? AND tooth = '26' ORDER BY id DESC LIMIT 1", (pid,))
        d = self.q("SELECT * FROM patient_documents WHERE chart_entry_id = ?", (e["id"],))
        self.assertEqual((d["category"], d["title"]), ("clinical_photo", "Tooth 26 · Caries (decay) (O)"))
        page = c.get(f"/staff/patients/{pid}?tab=chart&tooth=26").data.decode()
        self.assertIn(f"/staff/patients/{pid}/documents/{d['id']}", page)
        # a file that isn't a photo: nothing saved
        n = self.q("SELECT COUNT(*) AS n FROM chart_entries WHERE patient_id = ?", (pid,))["n"]
        c.post(f"/staff/patients/{pid}/chart", data={"tooth": "26", "condition": "caries", "photos": [(io.BytesIO(b"hello"), "x.png")]},
               content_type="multipart/form-data")
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM chart_entries WHERE patient_id = ?", (pid,))["n"], n)
