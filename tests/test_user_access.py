"""Individual access: add or remove single permissions for one user on top of their role."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402


class TestUserAccess(Base):
    def uid(self, who):
        return self.q("SELECT id FROM users WHERE email = ?", (who + DOMAIN,))["id"]

    def test_add_and_remove_for_one_person(self):
        a = self.login("admin")
        rid = self.uid("reception.malolos")
        page = a.get(f"/staff/admin/users/{rid}/access").data.decode()
        self.assertIn("Individual access", page)
        before = self.login("reception.malolos")
        self.assertEqual(before.get("/staff/expenses/").status_code, 403)
        from app.permissions import load_role_permissions
        role = load_role_permissions(self.conn, "receptionist")
        self.assertIn("patients.view", role)
        self.assertNotIn("expenses.view", role)
        wanted = (role - {"leads.view"}) | {"expenses.view"}
        a.post(f"/staff/admin/users/{rid}/access", data={"perm": sorted(wanted)})
        rows = {r["permission"]: r["granted"] for r in self.conn.all("SELECT * FROM user_permissions WHERE user_id = ?", (rid,))}
        self.assertEqual(rows, {"expenses.view": 1, "leads.view": 0})
        from app.permissions import load_user_permissions
        eff = load_user_permissions(self.conn, rid, "receptionist")
        self.assertIn("expenses.view", eff)
        self.assertNotIn("leads.view", eff)
        # another receptionist is unaffected
        other = self.conn.one("SELECT id FROM users WHERE access_role = 'receptionist' AND id != ? LIMIT 1", (rid,))
        if other:
            self.assertNotIn("expenses.view", load_user_permissions(self.conn, other["id"], "receptionist"))
        self.assertEqual(self.login("reception.malolos").get("/staff/expenses/").status_code, 200)
        self.assertIn("+ individual", a.get("/staff/admin/users?tab=staff").data.decode())
        # reset
        a.post(f"/staff/admin/users/{rid}/access", data={"action": "reset"})
        self.assertIsNone(self.q("SELECT 1 AS x FROM user_permissions WHERE user_id = ?", (rid,)))

    def test_locked_permissions_cannot_be_added(self):
        a = self.login("admin")
        rid = self.uid("reception.malolos")
        a.post(f"/staff/admin/users/{rid}/access", data={"perm": ["users.manage", "audit.view"]})
        self.assertIsNone(self.q("SELECT 1 AS x FROM user_permissions WHERE user_id = ? AND granted = 1 AND permission IN ('users.manage','audit.view')", (rid,)))

    def test_only_super_admin(self):
        d = self.login("dentist.malolos")
        self.assertEqual(d.get(f"/staff/admin/users/{self.uid('reception.malolos')}/access").status_code, 403)
