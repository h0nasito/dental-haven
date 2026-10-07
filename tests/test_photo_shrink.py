"""Lab case photos are made small on upload: at most 1600 px, JPEG, no GPS metadata."""
from __future__ import annotations

import io
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402


def big_photo() -> bytes:
    from PIL import Image
    im = Image.effect_noise((4000, 3000), 60).convert("RGB")     # noisy, like a real photo
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (14.0, 50.0, 0.0)}                # GPS info
    out = io.BytesIO()
    im.save(out, "JPEG", quality=95, exif=exif)
    return out.getvalue()


class TestPhotoShrink(Base):
    def test_shrink(self):
        from PIL import Image
        from app.uploads import shrink_photo
        data = big_photo()
        small = shrink_photo(data)
        self.assertLess(len(small), len(data) / 3)
        with Image.open(io.BytesIO(small)) as im:
            self.assertEqual(max(im.size), 1600)
            self.assertNotIn(0x8825, im.getexif())
        self.assertIsNone(shrink_photo(b"not an image"))

    def test_lab_case_upload_is_small(self):
        doc = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        pid = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (doc,))["id"]
        lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        d = self.login("dentist.malolos")
        data = big_photo()
        r = d.post("/staff/lab/new", data={"patient_id": pid, "lab_id": lab, "branch_id": self.branch("malolos"), "dentist_id": doc,
                                           "case_type": "Bridge", "teeth": "", "shade": "", "sent_on": date.today().isoformat(), "due_on": "",
                                           "lab_fee": "", "material": "", "instructions": "", "photos": [(io.BytesIO(data), "shade.jpg")]},
                   content_type="multipart/form-data")
        case_id = int(r.headers["Location"].rstrip("/").split("/")[-1])
        ph = self.q("SELECT * FROM lab_case_photos WHERE case_id = ?", (case_id,))
        self.assertTrue(ph["stored_name"].endswith(".jpg"))
        body = d.get(f"/staff/lab/{case_id}/photos/{ph['id']}").data
        self.assertLess(len(body), len(data) / 3)
