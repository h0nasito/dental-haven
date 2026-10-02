"""Patient profile photo: upload, show only to staff, replace, remove."""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00"
       b"\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82")


class TestPatientPhoto(Base):
    def test_upload_view_replace_remove(self):
        pid = self.q("SELECT id FROM patients WHERE active = 1 ORDER BY id LIMIT 1")["id"]
        self.conn.execute("UPDATE patients SET photo = NULL WHERE id = ?", (pid,))
        c = self.login("reception.malolos")
        page = c.get(f"/staff/patients/{pid}").data.decode()
        self.assertIn("Add photo", page)
        # not an image -> refused
        r = c.post(f"/staff/patients/{pid}/photo", data={"photo": (io.BytesIO(b"hello"), "x.png")},
                   content_type="multipart/form-data", follow_redirects=True)
        self.assertIsNone(self.q("SELECT photo FROM patients WHERE id = ?", (pid,))["photo"])
        c.post(f"/staff/patients/{pid}/photo", data={"photo": (io.BytesIO(PNG), "face.png")}, content_type="multipart/form-data")
        first = self.q("SELECT photo FROM patients WHERE id = ?", (pid,))["photo"]
        self.assertTrue(first.startswith("patient_photos/"))
        r = c.get(f"/staff/patients/{pid}/photo")
        self.assertEqual(r.status_code, 200)
        self.assertIn("no-store", r.headers["Cache-Control"])
        self.assertIn("Change photo", c.get(f"/staff/patients/{pid}").data.decode())
        # not reachable without signing in, and never under /static
        self.assertNotEqual(self.app.test_client().get(f"/staff/patients/{pid}/photo").status_code, 200)
        # replace: the old file is deleted
        from app.uploads import document_path
        with self.app.app_context():
            old_path = document_path(first)
        c.post(f"/staff/patients/{pid}/photo", data={"photo": (io.BytesIO(PNG), "face2.png")}, content_type="multipart/form-data")
        self.assertNotEqual(self.q("SELECT photo FROM patients WHERE id = ?", (pid,))["photo"], first)
        self.assertFalse(old_path.exists())
        # remove
        c.post(f"/staff/patients/{pid}/photo", data={"action": "remove"})
        self.assertIsNone(self.q("SELECT photo FROM patients WHERE id = ?", (pid,))["photo"])
        self.assertEqual(c.get(f"/staff/patients/{pid}/photo").status_code, 404)
        self.assertTrue(self.q("SELECT id FROM audit_log WHERE action = 'patient_photo_removed' AND entity_id = ?", (pid,)))
