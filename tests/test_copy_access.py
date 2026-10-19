"""Admin: copy another user's access (role + individual changes, optionally branches and labs)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402


class TestCopyAccess(Base):
    def test_copy_access(self):
        admin = self.login("admin")
        src = self.q("SELECT * FROM users WHERE email = ?", ("reception.malolos" + DOMAIN,))
        dst = self.q("SELECT * FROM users WHERE role != 'super_admin' AND id != ? AND email NOT LIKE 'reception.malolos%' ORDER BY id LIMIT 1", (src["id"],))
        self.conn.execute("INSERT INTO user_permissions (user_id, permission, granted) VALUES (?, 'deposits.view', 1)", (src["id"],))
        self.conn.execute("INSERT INTO user_permissions (user_id, permission, granted) VALUES (?, 'payroll.prepare', 1)", (dst["id"],))
        self.assertIn("Copy access from another user", admin.get(f"/staff/admin/users/{dst['id']}").data.decode())
        admin.post(f"/staff/admin/users/{dst['id']}/copy-access", data={"from_user": src["id"], "places": "1"})
        d = self.q("SELECT * FROM users WHERE id = ?", (dst["id"],))
        self.assertEqual((d["role"], d["access_role"] or d["role"]), (src["role"], src["access_role"] or src["role"]))
        perms = {r["permission"]: r["granted"] for r in self.conn.all("SELECT * FROM user_permissions WHERE user_id = ?", (dst["id"],))}
        self.assertEqual(perms, {"deposits.view": 1})
        b = lambda uid: sorted(r["branch_id"] for r in self.conn.all("SELECT branch_id FROM user_branches WHERE user_id = ?", (uid,)))
        self.assertEqual(b(dst["id"]), b(src["id"]))
        self.assertIsNotNone(self.q("SELECT id FROM audit_log WHERE action = 'user_access_copied' AND entity_id = ?", (dst["id"],)))
        # not from or to a super admin; only roles.manage
        sa = self.q("SELECT id FROM users WHERE role = 'super_admin' LIMIT 1")["id"]
        admin.post(f"/staff/admin/users/{dst['id']}/copy-access", data={"from_user": sa})
        self.assertNotEqual(self.q("SELECT role FROM users WHERE id = ?", (dst["id"],))["role"], "super_admin")
        self.assertEqual(self.login("reception.malolos").post(f"/staff/admin/users/{dst['id']}/copy-access",
                                                              data={"from_user": src["id"]}).status_code, 403)


class TestUsersLabTab(Base):
    def test_laboratory_tab(self):
        from app.auth import hash_password
        from app.util import now_str
        uid = self.conn.insert("users", {"email": "lab.tab@demo.dentalhaven.test", "name": "Lab Tab Person", "password_hash": hash_password("x" * 12),
                                         "role": "staff", "access_role": "lab_receptionist", "active": 1, "must_change_password": 0,
                                         "created_at": now_str()})
        lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        self.conn.execute("INSERT INTO user_labs (user_id, lab_id) VALUES (?, ?)", (uid, lab))
        admin = self.login("admin")
        lab_page = admin.get("/staff/admin/users?tab=lab").data.decode()
        self.assertIn("Lab Tab Person", lab_page)
        self.assertIn("DSDL", lab_page)
        self.assertNotIn("Lab Tab Person", admin.get("/staff/admin/users?tab=staff").data.decode())
        self.assertIn('Laboratory <span class="pill-n">', admin.get("/staff/admin/users").data.decode())
