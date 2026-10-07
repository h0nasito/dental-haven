"""The lab bills the branch for its lab cases: branch clients, lab invoice with branch cases, void frees them again."""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402


class TestLabCaseBilling(Base):
    def setUp(self):
        super().setUp()
        self.lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        doc = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        pid = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (doc,))["id"]
        d = self.login("dentist.malolos")
        r = d.post("/staff/lab/new", data={"patient_id": pid, "lab_id": self.lab, "branch_id": self.branch("malolos"), "dentist_id": doc,
                                           "case_type": "Bridge", "teeth": "14-16", "shade": "A2", "sent_on": date.today().isoformat(),
                                           "due_on": "", "lab_fee": "", "material": "", "instructions": ""})
        self.case = int(r.headers["Location"].rstrip("/").split("/")[-1])
        a = self.login("admin")
        r = a.post("/staff/admin/users/new", data={"name": "DSDL Lab Receptionist", "email": f"labrec{id(self)}@dsdl.test", "role": "staff",
                                                   "labs": [str(self.lab)], "position": "Lab Receptionist"})
        temp = re.search(rb'id="temp-pw"[^>]*>([^<]+)<', r.data).group(1).decode()
        uid = self.q("SELECT id FROM users WHERE email = ?", (f"labrec{id(self)}@dsdl.test",))["id"]
        self.conn.execute("INSERT INTO user_permissions (user_id, permission, granted) VALUES (?, 'lab.billing', 1)", (uid,))
        self.t = self.app.test_client()
        self.t.post("/staff/login", data={"email": f"labrec{id(self)}@dsdl.test", "password": temp})
        self.t.post("/staff/account/password", data={"current_password": temp, "new_password": "LabRec-2026x", "confirm_password": "LabRec-2026x"})

    def test_lab_sets_price_and_bills_branch(self):
        # the lab receptionist sets the price on the case
        self.t.post(f"/staff/lab/{self.case}", data={"status": "accepted", "lab_fee": "3500", "note": ""})
        self.assertEqual(self.q("SELECT lab_fee_cents FROM lab_cases WHERE id = ?", (self.case,))["lab_fee_cents"], 350000)
        inv_page = self.t.get("/staff/lab/invoices").data.decode()
        self.assertIn("Dental Haven Malolos (branch)", inv_page)
        client = self.q("SELECT id FROM lab_clients WHERE lab_id = ? AND branch_id = ?", (self.lab, self.branch("malolos")))
        page = self.t.get(f"/staff/lab/invoices/new?client={client['id']}").data.decode()
        self.assertIn(f"#{self.case}", page)
        r = self.t.post("/staff/lab/invoices/new", data={"client": client["id"], f"c_{self.case}": "1"})
        iid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        item = self.q("SELECT * FROM lab_invoice_items WHERE invoice_id = ?", (iid,))
        self.assertEqual((item["case_id"], item["amount_cents"]), (self.case, 350000))
        self.assertNotIn(self.q("SELECT last_name FROM patients p JOIN lab_cases c ON c.patient_id = p.id WHERE c.id = ?", (self.case,))["last_name"],
                         item["description"])
        self.assertEqual(self.q("SELECT invoice_id FROM lab_cases WHERE id = ?", (self.case,))["invoice_id"], iid)
        # issue, then the branch sees it was billed
        self.t.post(f"/staff/lab/invoices/{iid}", data={"action": "issue"})
        case_page = self.login("dentist.malolos").get(f"/staff/lab/{self.case}").data.decode()
        self.assertIn("Billed to the branch on lab invoice LI-", case_page)
        # not offered again; voiding frees it
        self.assertNotIn(f"name=\"c_{self.case}\"", self.t.get(f"/staff/lab/invoices/new?client={client['id']}").data.decode())
        self.t.post(f"/staff/lab/invoices/{iid}", data={"action": "void", "reason": "Wrong price"})
        self.assertIsNone(self.q("SELECT invoice_id FROM lab_cases WHERE id = ?", (self.case,))["invoice_id"])

    def test_bill_by_case_with_units_extras_and_less(self):
        r = self.t.post(f"/staff/lab/cases/{self.case}/bill")
        iid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        first = self.q("SELECT * FROM lab_invoice_items WHERE invoice_id = ?", (iid,))
        self.assertEqual(first["case_id"], self.case)
        # 10 units zirconia bridge x 5,500
        self.t.post(f"/staff/lab/invoices/{iid}", data={"action": "update_item", "item_id": first["id"], "description": "Zirconia bridge (per tooth)",
                                                        "qty": "10", "unit_price": "5500"})
        # casts 2 x 500, and 1 free unit less 5,500
        self.t.post(f"/staff/lab/invoices/{iid}", data={"action": "add_item", "case_id": self.case, "description": "Cast (upper and lower)",
                                                        "qty": "2", "unit_price": "500"})
        self.t.post(f"/staff/lab/invoices/{iid}", data={"action": "add_item", "case_id": self.case, "description": "1 free unit",
                                                        "qty": "1", "unit_price": "5500", "is_less": "1"})
        inv = self.q("SELECT * FROM lab_invoices WHERE id = ?", (iid,))
        self.assertEqual(inv["total_cents"], 5500000 + 100000 - 550000)
        self.assertEqual(self.q("SELECT lab_fee_cents FROM lab_cases WHERE id = ?", (self.case,))["lab_fee_cents"], 5050000)
        page = self.t.get(f"/staff/lab/invoices/{iid}/print").data.decode()
        for part in (f"Case #{self.case} · Bridge", "Zirconia bridge (per tooth)", "Less: 1 free unit", "−₱5,500.00", "₱50,500.00"):
            self.assertIn(part, page)
        # the case page now opens that invoice
        self.assertEqual(self.t.post(f"/staff/lab/cases/{self.case}/bill").headers["Location"].rstrip("/").split("/")[-1], str(iid))
        self.assertIn("Open lab invoice", self.t.get(f"/staff/lab/{self.case}").data.decode())

    def test_branch_cannot_bill(self):
        self.assertEqual(self.login("dentist.malolos").post(f"/staff/lab/cases/{self.case}/bill").status_code, 403)


class TestLabCasePhotos(Base):
    def test_photos_on_create_and_later_lab_can_see(self):
        import io
        from test_patient_profile import PNG
        import base64
        img = base64.b64decode(PNG)
        lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        doc = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        pid = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (doc,))["id"]
        d = self.login("dentist.malolos")
        r = d.post("/staff/lab/new", data={"patient_id": pid, "lab_id": lab, "branch_id": self.branch("malolos"), "dentist_id": doc,
                                           "case_type": "Bridge", "teeth": "", "shade": "A2", "sent_on": date.today().isoformat(), "due_on": "",
                                           "lab_fee": "", "material": "", "instructions": "",
                                           "photos": [(io.BytesIO(img), "shade.png"), (io.BytesIO(img), "upper.png")]},
                   content_type="multipart/form-data")
        case = int(r.headers["Location"].rstrip("/").split("/")[-1])
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM lab_case_photos WHERE case_id = ?", (case,))["n"], 2)
        d.post(f"/staff/lab/{case}/photos", data={"photos": [(io.BytesIO(img), "model.png")], "caption": "Model"}, content_type="multipart/form-data")
        rows = self.conn.all("SELECT * FROM lab_case_photos WHERE case_id = ? ORDER BY id", (case,))
        self.assertEqual((len(rows), rows[-1]["caption"]), (3, "Model"))
        page = d.get(f"/staff/lab/{case}").data.decode()
        self.assertIn("Reference photos", page)
        r = d.get(f"/staff/lab/{case}/photos/{rows[0]['id']}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("no-store", r.headers["Cache-Control"])
        # someone without access to the case can't open it
        self.assertIn(self.app.test_client().get(f"/staff/lab/{case}/photos/{rows[0]['id']}").status_code, (302, 401, 403))
        d.post(f"/staff/lab/{case}/photos", data={"action": "remove", "photo_id": rows[0]["id"]})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM lab_case_photos WHERE case_id = ?", (case,))["n"], 2)
