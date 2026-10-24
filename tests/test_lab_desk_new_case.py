"""Lab staff (a laboratory, no branch) add a branch lab case: find the patient by name/chart only, pick the branch."""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402


class TestLabDeskNewCase(Base):
    def setUp(self):
        super().setUp()
        self.lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        a = self.login("admin")
        email = f"labdesk{id(self)}@dsdl.test"
        r = a.post("/staff/admin/users/new", data={"name": "DSDL Desk", "email": email, "role": "staff", "labs": [str(self.lab)],
                                                   "position": "Laboratory Receptionist"})
        temp = re.search(rb'id="temp-pw"[^>]*>([^<]+)<', r.data).group(1).decode()
        self.uid = self.q("SELECT id FROM users WHERE email = ?", (email,))["id"]
        self.conn.execute("DELETE FROM user_branches WHERE user_id = ?", (self.uid,))
        self.conn.execute("INSERT INTO user_permissions (user_id, permission, granted) VALUES (?, 'lab.manage', 1)", (self.uid,))
        self.t = self.app.test_client()
        self.t.post("/staff/login", data={"email": email, "password": temp})
        self.t.post("/staff/account/password", data={"current_password": temp, "new_password": "LabDesk-2026x", "confirm_password": "LabDesk-2026x"})
        self.p = self.q("SELECT id, first_name, last_name, chart_no FROM patients WHERE active = 1 AND deleted_at IS NULL ORDER BY id LIMIT 1")

    def test_find_patient_and_add_case_for_a_branch(self):
        page = self.t.post("/staff/lab/new", data={"action": "search", "q": self.p["chart_no"]}).data.decode()
        self.assertIn(f"patient_id={self.p['id']}", page)
        form = self.t.get(f"/staff/lab/new?patient_id={self.p['id']}").data.decode()
        self.assertIn("Malolos", form)              # every branch can be chosen
        doc = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        r = self.t.post("/staff/lab/new", data={"patient_id": self.p["id"], "lab_id": self.lab, "branch_id": self.branch("malolos"),
                                                "dentist_id": doc, "case_type": "Bridge", "units": "1", "teeth": "14-16", "shade": "A2",
                                                "material": "", "lab_fee": "", "instructions": "", "sent_on": date.today().isoformat(), "due_on": ""})
        self.assertEqual(r.status_code, 302, r.data[:500])
        cid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        c = self.q("SELECT * FROM lab_cases WHERE id = ?", (cid,))
        self.assertEqual((c["branch_id"], c["created_by"], c["lab_id"]), (self.branch("malolos"), self.uid, self.lab))
        self.assertIsNotNone(self.q("SELECT id FROM notifications WHERE user_id = ? AND link = ?", (doc, f"/staff/lab/{cid}")))
        self.assertEqual(self.t.get(f"/staff/lab/{cid}").status_code, 200)

    def test_still_no_patient_records(self):
        self.assertEqual(self.t.get(f"/staff/patients/{self.p['id']}").status_code, 403)
        self.assertIn("0 records", self.t.get("/staff/patients/").data.decode())
