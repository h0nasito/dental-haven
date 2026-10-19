"""Profile pictures: cropped square, small JPEG without metadata; own or (users.manage) others'; served only to staff."""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_payroll_rules import TestPayrollRules  # noqa: E402


class TestProfilePicture(TestPayrollRules):
    for _n in [n for n in dir(TestPayrollRules) if n.startswith("test_")]:
        locals()[_n] = None

    def _photo(self):
        from PIL import Image
        im = Image.new("RGB", (3000, 2000), (200, 120, 90))
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"          # some metadata that must not survive
        b = io.BytesIO(); im.save(b, "JPEG", quality=95, exif=exif.tobytes()); b.seek(0)
        return b

    def test_profile_picture(self):
        from PIL import Image
        rec = self.login("reception.malolos")
        uid = self.q("SELECT id FROM users WHERE email LIKE 'reception.malolos@%'")["id"]
        self.assertEqual(rec.get("/staff/account").status_code, 200)
        r = rec.post("/staff/account/avatar", data={"photo": (self._photo(), "me.jpg")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        name = self.q("SELECT avatar FROM users WHERE id = ?", (uid,))["avatar"]
        self.assertTrue(name.endswith(".jpg"))
        img = rec.get(f"/media/avatar/{uid}/{name[:-4]}.jpg")
        self.assertEqual(img.status_code, 200)
        self.assertLess(len(img.data), 40_000)
        im = Image.open(io.BytesIO(img.data))
        self.assertEqual(im.size, (256, 256))
        self.assertFalse(dict(im.getexif()))
        self.assertIn(f"/media/avatar/{uid}/", rec.get("/staff/").data.decode())          # topbar
        # not shown to someone signed out
        self.assertNotEqual(self.app.test_client().get(f"/media/avatar/{uid}/{name[:-4]}.jpg").status_code, 200)
        # a non-image is refused
        bad = rec.post("/staff/account/avatar", data={"photo": (io.BytesIO(b"hello"), "x.txt")}, content_type="multipart/form-data")
        self.assertEqual(bad.status_code, 302)
        self.assertEqual(self.q("SELECT avatar FROM users WHERE id = ?", (uid,))["avatar"], name)
        # staff can't change someone else's; the admin can
        admin = self.login("admin")
        aid = self.q("SELECT id FROM users WHERE role = 'super_admin' LIMIT 1")["id"]
        self.assertEqual(rec.post("/staff/account/avatar", data={"user_id": aid, "action": "remove"}).status_code, 403)
        admin.post("/staff/account/avatar", data={"user_id": uid, "action": "remove"})
        self.assertIsNone(self.q("SELECT avatar FROM users WHERE id = ?", (uid,))["avatar"])


del TestPayrollRules
