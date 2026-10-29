"""Patient Uploads tab: up to 20 files at a time."""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402
from test_landing import tiny_png  # noqa: E402


class TestPatientUploads(Base):
    def _pid(self):
        return self.q("SELECT p.id FROM patients p JOIN branches b ON b.id = p.preferred_branch_id WHERE b.slug = 'malolos' LIMIT 1")["id"]

    def test_many_files(self):
        c = self.login("admin")
        pid = self._pid()
        before = self.conn.scalar("SELECT COUNT(*) FROM patient_documents WHERE patient_id = ?", (pid,))
        files = [(io.BytesIO(tiny_png()), f"x{i}.png") for i in range(3)]
        r = c.post(f"/staff/patients/{pid}/documents", content_type="multipart/form-data",
                   data={"category": "consent_form", "title": "Consent pages", "files": files})
        self.assertEqual(r.status_code, 302)
        rows = self.conn.all("SELECT title FROM patient_documents WHERE patient_id = ? ORDER BY id DESC LIMIT 3", (pid,))
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM patient_documents WHERE patient_id = ?", (pid,)), before + 3)
        self.assertEqual(sorted(r["title"] for r in rows), ["Consent pages (1)", "Consent pages (2)", "Consent pages (3)"])
        # more than 20 at once: refused
        many = [(io.BytesIO(tiny_png()), f"y{i}.png") for i in range(21)]
        c.post(f"/staff/patients/{pid}/documents", content_type="multipart/form-data", data={"category": "consent_form", "files": many})
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM patient_documents WHERE patient_id = ?", (pid,)), before + 3)
        # the page's one-by-one sending gets JSON back and keeps the numbering
        r = c.post(f"/staff/patients/{pid}/documents", content_type="multipart/form-data", headers={"X-Requested-With": "fetch"},
                   data={"category": "consent_form", "title": "Batch", "n": "7", "files": (io.BytesIO(tiny_png()), "z.png")})
        self.assertEqual(r.get_json(), {"ok": True, "saved": 1, "error": ""})
        self.assertTrue(self.q("SELECT id FROM patient_documents WHERE patient_id = ? AND title = 'Batch (7)'", (pid,)))
        bad = c.post(f"/staff/patients/{pid}/documents", content_type="multipart/form-data", headers={"X-Requested-With": "fetch"},
                     data={"category": "consent_form", "files": (io.BytesIO(b"not an image"), "bad.png")})
        self.assertEqual(bad.status_code, 400)
        page = c.get(f"/staff/patients/{pid}?tab=documents").data.decode()
        self.assertIn("up to 20 at a time", page)
