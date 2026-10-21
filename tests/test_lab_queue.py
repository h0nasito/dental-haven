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
        # the lab dashboard: counts, to-do, ongoing, ready
        self.assertIn("Laboratory", home)
        self.assertIn("New from branches", home)
        self.assertIn("To do", home)
        self.assertIn("overdue: finish or tell the clinic", home)
        self.assertIn("new case(s) from the branches to accept", home)
        self.assertIn("Ongoing cases &amp; works", home)
        self.assertIn("Denture QTEST", home)
        self.assertIn("Unpaid balance", home)
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

    def test_send_several_items_to_lab(self):
        lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        doc = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        pid = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (doc,))["id"]
        d = self.login("dentist.malolos")
        page = d.get(f"/staff/lab/new?patient_id={pid}").data.decode()
        self.assertIn("+ Add another item", page)
        before = self.q("SELECT COUNT(*) AS n FROM lab_cases")["n"]
        # e.g. 5 units of crowns: 2 zirconia (11, 12) and 3 E.max (21, 22, 23), both shade A2
        r = d.post("/staff/lab/new", data={"patient_id": pid, "lab_id": lab, "branch_id": self.branch("malolos"), "dentist_id": doc,
                                           "sent_on": date.today().isoformat(), "due_on": "", "instructions_all": "Rush please",
                                           "case_type": ["Crown (zirconia / all-ceramic)", "Crown (zirconia / all-ceramic)"],
                                           "units": ["2", "3"], "teeth": ["11, 12", "21, 22, 23"], "shade": ["A2", "A2"],
                                           "material": ["Zirconia", "E.max"], "lab_fee": ["11000", ""], "instructions": ["", "E.max press"]})
        self.assertEqual(r.status_code, 302)
        rows = self.conn.all("SELECT * FROM lab_cases WHERE patient_id = ? ORDER BY id DESC LIMIT 2", (pid,))[::-1]
        self.assertEqual([(c["units"], c["teeth"], c["shade"], c["material"], c["lab_fee_cents"]) for c in rows],
                         [(2, "11, 12", "A2", "Zirconia", 1100000), (3, "21, 22, 23", "A2", "E.max", None)])
        self.assertIn("E.max press", rows[1]["instructions"])
        self.assertIn("Rush please", rows[0]["instructions"])
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM lab_cases")["n"], before + 2)
        self.assertIn("3 × Crown (zirconia", d.get(f"/staff/lab/{rows[1]['id']}").data.decode())
        # an item with bad units: nothing is saved
        r = d.post("/staff/lab/new", data={"patient_id": pid, "lab_id": lab, "branch_id": self.branch("malolos"), "dentist_id": doc,
                                           "sent_on": date.today().isoformat(), "case_type": ["Bridge", "Bridge"], "units": ["1", "0"],
                                           "teeth": ["", ""], "shade": ["", ""], "material": ["", ""], "lab_fee": ["", ""], "instructions": ["", ""]})
        self.assertIn("Item 2: enter the number of units", r.data.decode())
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM lab_cases")["n"], before + 2)

    def test_material_list_and_new_material(self):
        lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        doc = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        pid = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (doc,))["id"]
        d = self.login("dentist.malolos")
        page = d.get(f"/staff/lab/new?patient_id={pid}").data.decode()
        self.assertIn("+ New material", page)
        self.assertIn(">Zirconia</option>", page)
        # crown in E.max (11, 12) and a bridge in zirconia (23-25), plus a new material typed in
        r = d.post("/staff/lab/new", data={"patient_id": pid, "lab_id": lab, "branch_id": self.branch("malolos"), "dentist_id": doc,
                                           "sent_on": date.today().isoformat(),
                                           "case_type": ["Crown (PFM)", "Bridge", "Veneer"], "units": ["2", "3", "1"],
                                           "teeth": ["11, 12", "23, 24, 25", "13"], "shade": ["A2", "A2", "A1"],
                                           "material": ["E.max (lithium disilicate)", "Zirconia", "__new__"], "material_new": ["", "", "Feldspathic QT"],
                                           "lab_fee": ["", "", ""], "instructions": ["", "", ""]})
        self.assertEqual(r.status_code, 302)
        rows = self.conn.all("SELECT material FROM lab_cases WHERE patient_id = ? ORDER BY id DESC LIMIT 3", (pid,))[::-1]
        self.assertEqual([x["material"] for x in rows], ["E.max (lithium disilicate)", "Zirconia", "Feldspathic QT"])
        self.assertIsNotNone(self.q("SELECT id FROM lab_materials WHERE name = 'Feldspathic QT'"))
        r = d.post("/staff/lab/new", data={"patient_id": pid, "lab_id": lab, "branch_id": self.branch("malolos"), "sent_on": date.today().isoformat(),
                                           "case_type": "Bridge", "units": "1", "material": "__new__", "material_new": ""})
        self.assertIn("type the new material", r.data.decode())

    def test_super_admin_removes_wrong_lab_case(self):
        lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        doc = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        pid = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (doc,))["id"]
        d = self.login("dentist.malolos")
        r = d.post("/staff/lab/new", data={"patient_id": pid, "lab_id": lab, "branch_id": self.branch("malolos"), "dentist_id": doc,
                                           "sent_on": date.today().isoformat(), "case_type": "Bridge", "units": "1", "teeth": "99 QT"})
        cid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        self.assertNotIn("Remove this lab case", d.get(f"/staff/lab/{cid}").data.decode())
        self.assertEqual(d.post(f"/staff/lab/{cid}/remove", data={"reason": "dup"}).status_code, 403)
        a = self.login("admin")
        self.assertIn("Remove this lab case", a.get(f"/staff/lab/{cid}").data.decode())
        a.post(f"/staff/lab/{cid}/remove", data={"reason": ""})                       # needs a reason
        self.assertIsNotNone(self.q("SELECT id FROM lab_cases WHERE id = ?", (cid,)))
        a.post(f"/staff/lab/{cid}/remove", data={"reason": "Duplicate entry"})
        self.assertIsNone(self.q("SELECT id FROM lab_cases WHERE id = ?", (cid,)))
        self.assertIsNone(self.q("SELECT id FROM lab_case_events WHERE case_id = ?", (cid,)))
        log = self.q("SELECT * FROM audit_log WHERE action = 'lab_case_removed' ORDER BY id DESC LIMIT 1")
        self.assertIn("Duplicate entry", log["summary"])
        # a billed case can't be removed
        r = d.post("/staff/lab/new", data={"patient_id": pid, "lab_id": lab, "branch_id": self.branch("malolos"), "dentist_id": doc,
                                           "sent_on": date.today().isoformat(), "case_type": "Bridge", "units": "1"})
        cid2 = int(r.headers["Location"].rstrip("/").split("/")[-1])
        self.conn.execute("INSERT INTO lab_invoices (lab_id, client_id, clinic_name, status, created_at, updated_at) "
                          "SELECT ?, id, clinic_name, 'draft', '2026-01-01', '2026-01-01' FROM lab_clients LIMIT 1", (lab,))
        iid = self.q("SELECT MAX(id) AS id FROM lab_invoices")["id"]
        self.conn.execute("INSERT INTO lab_invoice_items (invoice_id, case_id, description) VALUES (?, ?, 'x')", (iid, cid2))
        a.post(f"/staff/lab/{cid2}/remove", data={"reason": "Wrong"})
        self.assertIsNotNone(self.q("SELECT id FROM lab_cases WHERE id = ?", (cid2,)))
