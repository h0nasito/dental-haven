"""Patient uploads: give a file a name when uploading, rename it later, download it under that name."""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402
from test_patient_photo import PNG  # noqa: E402


class TestDocumentRename(Base):
    def test_name_on_upload_and_rename(self):
        pid = self.q("SELECT id FROM patients WHERE active = 1 ORDER BY id LIMIT 1")["id"]
        c = self.login("admin")
        page = c.get(f"/staff/patients/{pid}?tab=documents").data.decode()
        self.assertIn('name="title"', page)
        c.post(f"/staff/patients/{pid}/documents", data={"category": "xray", "title": "  Panoramic   x-ray / before ",
                                                         "file": (io.BytesIO(PNG), "IMG_0001.png")}, content_type="multipart/form-data")
        d = self.q("SELECT * FROM patient_documents WHERE patient_id = ? ORDER BY id DESC LIMIT 1", (pid,))
        self.assertEqual((d["title"], d["original_name"]), ("Panoramic x-ray - before", "IMG_0001.png"))
        page = c.get(f"/staff/patients/{pid}?tab=documents").data.decode()
        self.assertIn("<strong>Panoramic x-ray - before</strong>", page)
        # rename and change its type
        r = c.post(f"/staff/patients/{pid}/documents/{d['id']}/rename", data={"title": "Periapical 36 after RCT", "category": "clinical_photo"})
        self.assertEqual(r.status_code, 302)
        d = self.q("SELECT * FROM patient_documents WHERE id = ?", (d["id"],))
        self.assertEqual((d["title"], d["category"]), ("Periapical 36 after RCT", "clinical_photo"))
        r = c.get(f"/staff/patients/{pid}/documents/{d['id']}?download=1")
        self.assertIn("Periapical 36 after RCT.png", r.headers["Content-Disposition"])
        r.close()
        # clearing the name shows the original file name again
        c.post(f"/staff/patients/{pid}/documents/{d['id']}/rename", data={"title": ""})
        self.assertEqual(self.q("SELECT title FROM patient_documents WHERE id = ?", (d["id"],))["title"], "")
        r = c.get(f"/staff/patients/{pid}/documents/{d['id']}?download=1")
        self.assertIn("IMG_0001.png", r.headers["Content-Disposition"])
        r.close()
