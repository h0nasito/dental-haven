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


class TestOralExam(Base):
    def test_soft_tissue_and_occlusion(self):
        pid = self.q("SELECT id FROM patients WHERE active = 1 ORDER BY id DESC LIMIT 1")["id"]
        c = self.login("admin")
        page = c.get(f"/staff/patients/{pid}?tab=chart&view=oral").data.decode()
        self.assertIn("No soft tissue or occlusion exam recorded yet", page)
        r = c.post(f"/staff/patients/{pid}/oral-exam", data={
            "exam_date": "2026-10-01", "gingivitis": "mild", "gingivitis_extent": "generalized", "periodontitis": "none",
            "periodontitis_extent": "localized", "frenum": "high", "tongue": "normal", "buccal_mucosa": "normal", "palate": "high_vault",
            "molar_right": "I", "molar_left": "II", "canine_right": "I", "canine_left": "na", "tongue_x": "bad"})
        self.assertEqual(r.status_code, 302)
        x = self.q("SELECT * FROM oral_exams WHERE patient_id = ? ORDER BY id DESC LIMIT 1", (pid,))
        self.assertEqual((x["gingivitis"], x["gingivitis_extent"], x["periodontitis_extent"], x["molar_left"], x["canine_left"]),
                         ("mild", "generalized", "", "II", "na"))
        page = c.get(f"/staff/patients/{pid}?tab=chart&view=oral").data.decode()
        self.assertIn("Generalized mild gingivitis", page)
        self.assertIn("High frenum attachment", page)
        self.assertIn("Cannot be determined", page)
        self.assertIn('value="II" selected', page)          # the form starts from the last exam
        # a second exam keeps the first as history
        c.post(f"/staff/patients/{pid}/oral-exam", data={"exam_date": "2026-10-20", "gingivitis": "none", "tongue": "tongue_tied"})
        page = c.get(f"/staff/patients/{pid}?tab=chart&view=oral").data.decode()
        self.assertIn("Earlier exams (1)", page)
        self.assertIn("Tongue-tied", page)
        # bad values are ignored; nothing chosen -> not saved
        n = self.q("SELECT COUNT(*) AS n FROM oral_exams WHERE patient_id = ?", (pid,))["n"]
        c.post(f"/staff/patients/{pid}/oral-exam", data={"tongue": "<b>"})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM oral_exams WHERE patient_id = ?", (pid,))["n"], n)
        # the teeth view shows a one-line summary
        self.assertIn("Soft tissue &amp; occlusion</a>", c.get(f"/staff/patients/{pid}?tab=chart").data.decode())


class TestChartBatch(Base):
    def test_save_several_teeth_at_once(self):
        import json
        pid = self.q("SELECT id FROM patients WHERE active = 1 ORDER BY id LIMIT 1 OFFSET 2")["id"]
        c = self.login("admin")
        before = self.q("SELECT COUNT(*) AS n FROM chart_entries WHERE patient_id = ? AND deleted = 0", (pid,))["n"]
        items = [{"tooth": "17", "condition": "caries", "surfaces": "OD"}, {"tooth": "46", "condition": "missing", "surfaces": ""},
                 {"tooth": "11", "condition": "restoration", "surfaces": "MXB", "note": "composite"}]
        r = c.post(f"/staff/patients/{pid}/chart", data={"items": json.dumps(items), "recorded_on": "2026-10-01", "tooth": "11", "condition": "sound"})
        self.assertEqual(r.status_code, 302)
        rows = self.conn.all("SELECT tooth, condition, surfaces, note, recorded_on FROM chart_entries WHERE patient_id = ? AND deleted = 0 "
                             "ORDER BY id DESC LIMIT 3", (pid,))[::-1]
        self.assertEqual([(x["tooth"], x["condition"], x["surfaces"], x["note"]) for x in rows],
                         [("17", "caries", "OD", ""), ("46", "missing", "", ""), ("11", "restoration", "MB", "composite")])
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM chart_entries WHERE patient_id = ? AND deleted = 0", (pid,))["n"], before + 3)
        # one bad entry: nothing saved
        c.post(f"/staff/patients/{pid}/chart", data={"items": json.dumps([{"tooth": "17", "condition": "caries"}, {"tooth": "99", "condition": "caries"}])})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM chart_entries WHERE patient_id = ? AND deleted = 0", (pid,))["n"], before + 3)
        page = c.get(f"/staff/patients/{pid}?tab=chart").data.decode()
        self.assertIn('id="chart-pending"', page)
        self.assertIn("data-hist=", page)
