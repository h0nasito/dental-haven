"""Laboratory receptionist: own access role (lab only), and a Work queue about the lab's work."""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402


class TestLabQueue(Base):
    def test_lab_receptionist_role_and_queue(self):
        from app.permissions import ACCESS_FOR_POSITION, POSITIONS, ROLES
        self.assertIn("Laboratory Receptionist", POSITIONS)
        self.assertEqual(ACCESS_FOR_POSITION["Laboratory Receptionist"], "lab_receptionist")
        self.assertIn("lab_receptionist", ROLES)
        lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        doc = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        pid = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (doc,))["id"]
        # a branch sends a case to the lab
        d = self.login("dentist.malolos")
        r = d.post("/staff/lab/new", data={"patient_id": pid, "lab_id": lab, "branch_id": self.branch("malolos"), "dentist_id": doc,
                                           "case_type": "Bridge", "teeth": "14-16", "shade": "A2", "sent_on": date.today().isoformat(),
                                           "due_on": "", "lab_fee": "", "material": "", "instructions": ""})
        case = int(r.headers["Location"].rstrip("/").split("/")[-1])
        # the admin creates the laboratory receptionist with the new role
        a = self.login("admin")
        email = f"labq{id(self)}@dsdl.test"
        r = a.post("/staff/admin/users/new", data={"name": "Lab Desk Q", "email": email, "role": "lab_receptionist",
                                                   "labs": [str(lab)], "position": "Laboratory Receptionist"})
        temp = re.search(rb'id="temp-pw"[^>]*>([^<]+)<', r.data).group(1).decode()
        u = self.q("SELECT * FROM users WHERE email = ?", (email,))
        self.assertEqual((u["role"], u["access_role"]), ("staff", "lab_receptionist"))
        t = self.app.test_client()
        t.post("/staff/login", data={"email": email, "password": temp})
        t.post("/staff/account/password", data={"current_password": temp, "new_password": "LabDesk-2026x", "confirm_password": "LabDesk-2026x"})
        # no clinic patients or bookings
        self.assertEqual(t.get("/staff/patients/").status_code, 403)
        # an overdue outside work for this lab
        client = self.conn.insert("lab_clients", {"lab_id": lab, "clinic_name": "QTest Clinic", "created_at": "2026-01-01 00:00:00"})
        work = self.conn.insert("lab_works", {"number": f"QW-{id(self)}", "lab_id": lab, "client_id": client, "clinic_name": "QTest Clinic",
                                              "case_type": "Denture QTEST", "status": "fabricating", "received_on": "2026-01-01",
                                              "due_on": (date.today() - timedelta(days=2)).isoformat(), "created_by": u["id"],
                                              "created_at": "2026-01-01 00:00:00", "updated_at": "2026-01-01 00:00:00"})
        page = t.get("/staff/queue").data.decode()
        self.assertIn("New from branches", page)
        self.assertIn(f"/staff/lab/{case}", page)
        self.assertIn("Denture QTEST", page)
        self.assertIn("overdue", page)
        self.assertIn("Unpaid invoices past due", page)          # has lab billing
        self.assertNotIn("Booking requests", page)                 # not the clinic's queue
        self.assertNotIn('view=clinic', page)                      # no clinic tab
        home = t.get("/staff/").data.decode()
        self.assertRegex(home, r'Work queue</span><span class="count">\d+')
        # the clinic receptionist still gets the clinic queue
        rec = self.login("reception.malolos").get("/staff/queue").data.decode()
        self.assertIn("Booking requests", rec)
        self.assertNotIn("New from branches", rec)
        # the admin assigned to the lab sees both, as tabs
        aid = self.q("SELECT id FROM users WHERE email = ?", ("admin" + DOMAIN,))
        if aid:
            self.conn.execute("INSERT OR IGNORE INTO user_labs (user_id, lab_id) VALUES (?, ?)", (aid["id"], lab))
            both = a.get("/staff/queue?view=lab").data.decode()
            self.assertIn("New from branches", both)
            self.assertIn("view=clinic", both)
        self.conn.execute("UPDATE lab_works SET status = 'cancelled' WHERE id = ?", (work,))
