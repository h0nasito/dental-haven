"""Production setup: first admin from settings, disk paths, gallery served from the data folder, backups."""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402
from test_landing import tiny_png  # noqa: E402

from app import create_app  # noqa: E402
from app.db import standalone_connection  # noqa: E402
from app.migrate import run_migrations  # noqa: E402


class TestProductionSetup(Base):
    def test_backup_download(self):
        c = self.login("admin")
        c.post("/staff/admin/content/gallery", content_type="multipart/form-data", data={
            "action": "add", "title": "Backup check", "authorization_note": "x", "authorized": "1",
            "image": (io.BytesIO(tiny_png()), "a.png")})
        r = c.post("/staff/admin/system/backup")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/zip")
        names = zipfile.ZipFile(io.BytesIO(r.data)).namelist()
        self.assertIn("dental_haven.db", names)
        self.assertTrue(any(n.startswith("website-images/gallery/") for n in names))
        self.assertIsNotNone(self.q("SELECT id FROM audit_log WHERE action = 'backup_downloaded'"))
        self.assertEqual(self.login("staff.malolos").post("/staff/admin/system/backup").status_code, 403)
        # the gallery image is served from PUBLIC_UPLOAD_DIR
        g = self.q("SELECT image_path FROM gallery_items WHERE title = 'Backup check'")
        self.assertEqual(self.app.test_client().get("/static/" + g["image_path"]).status_code, 200)


class TestDataDirAndFirstAdmin(__import__("unittest").TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_data_dir_and_ensure_admin(self):
        env = {"DATA_DIR": self.tmp, "APP_ENV": "production", "SECRET_KEY": "x" * 32,
               "INITIAL_ADMIN_EMAIL": "Owner@Clinic.test", "INITIAL_ADMIN_NAME": "Clinic Owner", "INITIAL_ADMIN_PASSWORD": "weak"}
        with mock.patch.dict(os.environ, env):
            os.environ.pop("DATABASE_URL", None)
            app = create_app()
            self.assertEqual(app.config["DATABASE_URL"], f"sqlite:///{Path(self.tmp) / 'dental_haven.db'}")
            self.assertEqual(app.config["UPLOAD_DIR"], str(Path(self.tmp) / "uploads"))
            self.assertEqual(app.config["PUBLIC_UPLOAD_DIR"], str(Path(self.tmp) / "public"))
            conn = standalone_connection(app.config["DATABASE_URL"])
            run_migrations(conn, verbose=False)
            runner = app.test_cli_runner()
            self.assertEqual(runner.invoke(args=["seed-base"]).exit_code, 0)
            self.assertNotEqual(runner.invoke(args=["seed-demo"]).exit_code, 0)  # refused in production
            r = runner.invoke(args=["ensure-admin"])  # weak password is rejected
            self.assertNotEqual(r.exit_code, 0)
            os.environ["INITIAL_ADMIN_PASSWORD"] = "Strong-Pass-2026"
            r = runner.invoke(args=["ensure-admin"])
            self.assertEqual(r.exit_code, 0, r.output)
            u = conn.one("SELECT * FROM users WHERE email = 'owner@clinic.test'")
            self.assertEqual((u["role"], u["must_change_password"]), ("super_admin", 1))
            r = runner.invoke(args=["ensure-admin"])  # second run does nothing
            self.assertIn("already exists", r.output)
            self.assertEqual(conn.scalar("SELECT COUNT(*) FROM users"), 1)
            self.assertEqual(conn.scalar("SELECT COUNT(*) FROM patients"), 0)  # no demo data
            conn.raw.close()
