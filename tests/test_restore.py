"""Restore a backup from Backup & download: upload in pieces, check, review, type RESTORE, safety copy, undo."""
from __future__ import annotations

import io
import re
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestRestore(Base):
    def backup_zip(self, c, parts=("database", "files")):
        c.post("/staff/admin/backup", data={"parts": list(parts)})
        link = re.findall(r'href="(/staff/admin/backup/[0-9a-f]+/download)"', c.get("/staff/admin/backup").data.decode())[0]
        return c.get(link).data

    def upload(self, c, data: bytes, name="backup.zip", chunk=50_000):
        jid = c.post("/staff/admin/backup/restore/start", data={"name": name}).get_json()["id"]
        off = 0
        while off < len(data):
            r = c.post(f"/staff/admin/backup/restore/{jid}/chunk?offset={off}", data=data[off:off + chunk],
                       content_type="application/octet-stream")
            self.assertEqual(r.status_code, 200, r.data)
            off = r.get_json()["size"]
        c.post(f"/staff/admin/backup/restore/{jid}/finish")
        return jid

    def test_restore_and_undo(self):
        c = self.login("admin")
        pid = self.q("SELECT id FROM patients ORDER BY id LIMIT 1")["id"]
        name = self.q("SELECT last_name FROM patients WHERE id = ?", (pid,))["last_name"]
        upl = Path(self.app.config["UPLOAD_DIR"]) / "restore-check.txt"
        upl.write_text("old file")
        data = self.backup_zip(c)
        # things change after the backup
        self.conn.execute("UPDATE patients SET last_name = 'Changed' WHERE id = ?", (pid,))
        upl.write_text("new file")
        (Path(self.app.config["UPLOAD_DIR"]) / "added-later.txt").write_text("x")
        jid = self.upload(c, data)
        page = c.get(f"/staff/admin/backup/restore/{jid}").data.decode()
        for part in ("In the backup", "In the system now", "Type <strong>RESTORE</strong>", "safety copy"):
            self.assertIn(part, page)
        # needs the word
        c.post(f"/staff/admin/backup/restore/{jid}", data={"confirm": "yes", "with_files": "1"})
        self.assertEqual(self.q("SELECT last_name FROM patients WHERE id = ?", (pid,))["last_name"], "Changed")
        c.post(f"/staff/admin/backup/restore/{jid}", data={"confirm": "restore", "with_files": "1"})
        self.assertEqual(self.q("SELECT last_name FROM patients WHERE id = ?", (pid,))["last_name"], name)
        self.assertEqual(upl.read_text(), "old file")
        self.assertFalse((Path(self.app.config["UPLOAD_DIR"]) / "added-later.txt").exists())
        self.assertIsNotNone(self.q("SELECT id FROM audit_log WHERE action = 'backup_restored'"))
        # everyone was logged out
        self.assertEqual(c.get("/staff/admin/backup").status_code, 302)
        c = self.login("admin")
        self.assertIn("Restored", c.get(f"/staff/admin/backup/restore/{jid}").data.decode())
        # undo with the safety copy: the change made after the backup comes back
        sid = re.findall(r'/staff/admin/backup/safety/(before-restore-[0-9a-f_-]+)/restore', c.get("/staff/admin/backup").data.decode())[0]
        r = c.post(f"/staff/admin/backup/safety/{sid}/restore")
        jid2 = r.headers["Location"].rstrip("/").split("/")[-1]
        c.post(f"/staff/admin/backup/restore/{jid2}", data={"confirm": "RESTORE", "with_files": "1"})
        self.assertEqual(self.q("SELECT last_name FROM patients WHERE id = ?", (pid,))["last_name"], "Changed")
        self.assertEqual(upl.read_text(), "new file")

    def test_bad_uploads(self):
        c = self.login("admin")
        jid = self.upload(c, b"not a zip at all")
        self.assertIn("a zip file. Choose", c.get(f"/staff/admin/backup/restore/{jid}").data.decode())
        jid = self.upload(c, self.backup_zip(c, ("excel",)))
        self.assertIn("no database", c.get(f"/staff/admin/backup/restore/{jid}").data.decode())
        # a backup from a newer version is refused
        data = self.backup_zip(c, ("database",))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "db"
            p.write_bytes(zipfile.ZipFile(io.BytesIO(data)).read("dental_haven.db"))
            db = sqlite3.connect(p)
            db.execute("INSERT INTO schema_migrations (name, applied_at) VALUES ('999_future.sql', '2030-01-01')")
            db.commit()
            db.close()
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.write(p, "dental_haven.db")
        jid = self.upload(c, buf.getvalue())
        self.assertIn("newer version", c.get(f"/staff/admin/backup/restore/{jid}").data.decode())
        self.assertEqual(c.post(f"/staff/admin/backup/restore/{jid}", data={"confirm": "RESTORE"}).status_code, 409)
        # pieces out of order are refused
        jid = c.post("/staff/admin/backup/restore/start", data={"name": "x.zip"}).get_json()["id"]
        self.assertEqual(c.post(f"/staff/admin/backup/restore/{jid}/chunk?offset=10", data=b"abc",
                                content_type="application/octet-stream").status_code, 409)

    def test_only_super_admin(self):
        s = self.login("staff.malolos")
        self.assertEqual(s.post("/staff/admin/backup/restore/start", data={"name": "x.zip"}).status_code, 403)
        self.assertEqual(s.get("/staff/admin/backup/restore/abc").status_code, 403)
