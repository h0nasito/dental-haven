"""Outside works from one of our branches can be moved to Branch cases (patient and dentist chosen; everything moves)."""
from __future__ import annotations

import re
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402


class TestLabWorkMove(Base):
    def setUp(self):
        super().setUp()
        from app.util import now_str, today
        self.lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        self.a = self.login("admin")
        self.branch_id = self.branch("malolos")
        cl = self.q("SELECT id FROM lab_clients WHERE lab_id = ? AND branch_id = ?", (self.lab, self.branch_id))
        self.client_id = cl["id"] if cl else self.conn.insert("lab_clients", {"lab_id": self.lab, "clinic_name": "Dental Haven Malolos (branch)",
                                                                               "branch_id": self.branch_id, "created_at": now_str()})
        self.p = self.q("SELECT id, first_name, last_name, chart_no FROM patients WHERE active = 1 AND deleted_at IS NULL ORDER BY id DESC LIMIT 1")
        self.doc = self.q("SELECT id, name FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))
        r = self.a.post("/staff/lab/works/new", data={
            "lab_id": self.lab, "clinic_name": "Dental Haven Malolos (branch)", "doctor": self.doc["name"], "patient_ref": f"{self.p['first_name']} {self.p['last_name']}",
            "case_type": ["Bridge", "Crown (PFM)"], "units": ["3", "1"], "arch": ["upper", ""], "teeth": ["14-16", "26"], "shade": ["A2", "A3"],
            "price": ["5000", "4000"], "discount": ["10%", ""], "received_on": today().isoformat(), "due_on": (today() + timedelta(days=5)).isoformat(),
            "x_desc": ["Rush fee"], "x_qty": ["1"], "x_price": ["1000"], "x_case": ["0"]})
        self.assertEqual(r.status_code, 302, r.data[:2000])
        self.w = self.q("SELECT * FROM lab_works ORDER BY id DESC LIMIT 1")
        self.conn.execute("UPDATE lab_works SET client_id = ? WHERE id = ?", (self.client_id, self.w["id"]))

    def test_move_keeps_everything(self):
        self.assertIn("Move to Branch cases", self.a.get(f"/staff/lab/works/{self.w['id']}").data.decode())
        self.a.post(f"/staff/lab/works/{self.w['id']}", data={"status": "designing", "note": "started", "delivered_on": ""})
        bill = self.a.post(f"/staff/lab/works/{self.w['id']}/bill")
        iid = int(bill.headers["Location"].rstrip("/").split("/")[-1])
        billed = self.q("SELECT total_cents FROM lab_invoices WHERE id = ?", (iid,))["total_cents"]
        page = self.a.get(f"/staff/lab/works/{self.w['id']}/move-to-branch").data.decode()
        self.assertIn(self.p["chart_no"], page)                       # found by the patient reference
        self.assertIn(f'value="{self.doc["id"]}" selected', page)       # dentist matched by name
        r = self.a.post(f"/staff/lab/works/{self.w['id']}/move-to-branch", data={"action": "move", "patient_id": self.p["id"], "dentist_id": self.doc["id"]})
        self.assertEqual(r.status_code, 302)
        cid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        c = self.q("SELECT * FROM lab_cases WHERE id = ?", (cid,))
        self.assertEqual((c["branch_id"], c["patient_id"], c["dentist_id"], c["status"], c["invoice_id"]),
                         (self.branch_id, self.p["id"], self.doc["id"], "designing", iid))
        items = self.conn.all("SELECT * FROM lab_case_items WHERE case_id = ? ORDER BY sort_order", (cid,))
        self.assertEqual([(i["case_type"], i["units"], i["lab_fee_cents"]) for i in items], [("Bridge", 3, 1350000), ("Crown (PFM)", 1, 400000)])
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM lab_case_extras WHERE case_id = ?", (cid,))["n"], 1)
        self.assertEqual(c["lab_fee_cents"], billed)
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM lab_invoice_items WHERE invoice_id = ? AND case_id = ?", (iid, cid))["n"],
                         self.q("SELECT COUNT(*) AS n FROM lab_invoice_items WHERE invoice_id = ?", (iid,))["n"])
        self.assertIn(self.w["number"], c["instructions"])
        self.assertTrue(self.q("SELECT COUNT(*) AS n FROM lab_case_events WHERE case_id = ? AND note = 'started'", (cid,))["n"])
        self.assertIsNone(self.q("SELECT id FROM lab_works WHERE id = ?", (self.w["id"],)))
        self.assertEqual(self.a.get(f"/staff/lab/{cid}").status_code, 200)

    def test_only_branch_works(self):
        from app.util import now_str
        other = self.conn.insert("lab_clients", {"lab_id": self.lab, "clinic_name": "Smile Bright", "created_at": now_str()})
        self.conn.execute("UPDATE lab_works SET client_id = ? WHERE id = ?", (other, self.w["id"]))
        self.assertNotIn("Move to Branch cases", self.a.get(f"/staff/lab/works/{self.w['id']}").data.decode())
        r = self.a.post(f"/staff/lab/works/{self.w['id']}/move-to-branch", data={"action": "move", "patient_id": self.p["id"]})
        self.assertEqual(r.status_code, 302)
        self.assertIsNotNone(self.q("SELECT id FROM lab_works WHERE id = ?", (self.w["id"],)))
