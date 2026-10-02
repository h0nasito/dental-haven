"""Patient list clean-up: find records with junk names, delete several at once, see deleted patients, restore."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestPatientCleanup(Base):
    def _junk(self, last, first):
        from app.util import now_str
        n = self.conn.scalar("SELECT COUNT(*) FROM patients") + 1
        return self.conn.insert("patients", {"first_name": first, "last_name": last, "chart_no": f"JUNK-{n}", "active": 1,
                                             "created_at": now_str(), "updated_at": now_str()})

    def test_find_delete_many_and_restore(self):
        j1, j2, j3 = self._junk(",,", "-"), self._junk("...", "Ma"), self._junk("-", "...")
        real = self.q("SELECT id FROM patients WHERE active = 1 AND last_name GLOB '*[a-z]*' AND first_name GLOB '*[a-z]*' LIMIT 1")
        admin = self.login("admin")
        page = admin.get("/staff/patients/?show=incomplete").data.decode()
        for j in (j1, j2, j3):
            self.assertIn(f'name="ids" value="{j}"', page)
        self.assertNotIn(f'name="ids" value="{real["id"]}"', page)
        self.assertIn("Delete selected", page)
        # a reason is required
        r = admin.post("/staff/patients/bulk", data={"action": "delete", "ids": [j1, j2], "next": "/staff/patients/?show=incomplete"},
                       follow_redirects=True)
        self.assertIn("Give a reason", r.data.decode())
        self.assertEqual(self.q("SELECT active FROM patients WHERE id = ?", (j1,))["active"], 1)
        r = admin.post("/staff/patients/bulk", data={"action": "delete", "ids": [j1, j2, j3], "reason": "Junk import rows",
                                                     "next": "/staff/patients/?show=incomplete"}, follow_redirects=True)
        self.assertIn("Deleted 3 patient(s)", r.data.decode())
        row = self.q("SELECT active, deleted_reason, deleted_by FROM patients WHERE id = ?", (j1,))
        self.assertEqual((row["active"], row["deleted_reason"]), (0, "Junk import rows"))
        self.assertTrue(row["deleted_by"])
        self.assertNotIn(f'name="ids" value="{j1}"', admin.get("/staff/patients/?show=incomplete").data.decode())
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM audit_log WHERE action = 'patient_deleted' AND entity_id IN (?, ?, ?)",
                                          (j1, j2, j3)), 3)
        # the deleted list shows them with the reason; restore puts them back
        page = admin.get("/staff/patients/?show=deleted").data.decode()
        self.assertIn("Junk import rows", page)
        self.assertIn("Restore selected", page)
        admin.post("/staff/patients/bulk", data={"action": "restore", "ids": [j2]})
        self.assertEqual(self.q("SELECT active, deleted_reason FROM patients WHERE id = ?", (j2,))["active"], 1)
        # roles without the delete permission can't delete or see the deleted list
        rec = self.login("reception.malolos")
        self.assertEqual(rec.post("/staff/patients/bulk", data={"action": "delete", "ids": [j2], "reason": "x"}).status_code, 403)
        self.assertNotIn("Deleted patients", rec.get("/staff/patients/?show=deleted").data.decode())
        # outside redirect targets are ignored
        r = admin.post("/staff/patients/bulk", data={"action": "delete", "ids": [j2], "reason": "x", "next": "https://evil.example/"})
        self.assertTrue(r.headers["Location"].endswith("/staff/patients/"))
