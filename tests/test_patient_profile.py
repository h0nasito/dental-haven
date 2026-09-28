"""Patient profile: grouped progress notes with prices, remarks, diagnosis, and split payments signed by the patient."""
from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402

# a real (tiny) PNG, as a signature pad would send it
PNG = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000010000000100806000000"
    "1ff3ff610000002949444154789c63f8ffff3f032580f1a0e0ff28a2c1"
    "a0018c1a3068c0a0018c1a306880010600a4e6ff01b0b41f4c00000000"
    "49454e44ae426082")).decode()


class TestPatientProfile(Base):
    def _patient_with_dentist(self):
        d = self.q("SELECT id FROM users WHERE email = ?", ("dentist.sjdm@demo.dentalhaven.test",))
        pid = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (d["id"],))["id"]
        return d["id"], pid

    def test_tabs_and_header(self):
        _d, pid = self._patient_with_dentist()
        admin = self.login("admin")
        page = admin.get(f"/staff/patients/{pid}").data.decode()
        for part in ("Progress Notes", "Treatment Plan", "Charts", "Bills &amp; Payment", "Prescriptions", "Certificates", "Uploads",
                     "Remarks", "Diagnosis", "Last visit", "Care info", "Patient record"):
            self.assertIn(part, page)
        for tab in ("notes", "plans", "chart", "billing", "rx", "certs", "documents", "remarks", "diagnosis", "changes", "clinical", "overview"):
            self.assertEqual(admin.get(f"/staff/patients/{pid}?tab={tab}").status_code, 200, tab)
        # front desk can't open the clinical tabs
        pid2 = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (self.branch("bocaue"),))["id"]
        front = self.login("staff.bocaue")
        for tab in ("notes", "diagnosis", "certs"):
            self.assertEqual(front.get(f"/staff/patients/{pid2}?tab={tab}").status_code, 403, tab)
        self.assertEqual(front.get(f"/staff/patients/{pid2}?tab=remarks").status_code, 200)

    def test_progress_notes_grouped_with_price(self):
        from app.util import now_str
        doc, pid = self._patient_with_dentist()
        sjdm = self.branch("sjdm")
        day = "2025-02-03"
        self.conn.insert("procedures", {"patient_id": pid, "branch_id": sjdm, "tooth": "35", "description": "Rebracket - Ordinary",
                                        "status": "completed", "performed_by": doc, "performed_at": day, "created_at": now_str()})
        inv = self.conn.insert("invoices", {"number": "TEST-PN-1", "branch_id": sjdm, "patient_id": pid, "status": "issued", "issued_at": day,
                                            "subtotal_cents": 95000, "total_cents": 95000, "created_at": now_str()})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Rebracket - Ordinary", "qty": 1, "unit_price_cents": 45000,
                                           "amount_cents": 45000, "dentist_id": doc, "done_on": day, "tooth": "35"})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Braces Adjustment", "qty": 1, "unit_price_cents": 50000,
                                           "amount_cents": 50000, "dentist_id": doc, "done_on": day})
        page = self.login("admin").get(f"/staff/patients/{pid}?tab=notes").data.decode()
        self.assertIn("Rebracket - Ordinary", page)
        self.assertIn("(#35)", page)
        self.assertIn("₱450.00", page)
        self.assertIn("Braces Adjustment", page)   # billed line without a procedure record still shows
        self.assertIn("TEST-PN-1", page)
        self.assertEqual(page.count("Rebracket - Ordinary</span>") + page.count("Rebracket - Ordinary <span"), 1)

    def test_remarks_and_diagnosis(self):
        _d, pid = self._patient_with_dentist()
        admin = self.login("admin")
        admin.post(f"/staff/patients/{pid}/remarks", data={"body": "Prefers text messages"})
        self.assertIn("Prefers text messages", admin.get(f"/staff/patients/{pid}?tab=remarks").data.decode())
        rid = self.q("SELECT id FROM patient_remarks WHERE patient_id = ?", (pid,))["id"]
        admin.post(f"/staff/patients/{pid}/remarks", data={"action": "delete", "remark_id": rid})
        self.assertEqual(self.q("SELECT deleted FROM patient_remarks WHERE id = ?", (rid,))["deleted"], 1)
        doc = self.login("dentist.sjdm")
        doc.post(f"/staff/patients/{pid}/diagnoses", data={"diagnosis": "Irreversible pulpitis", "tooth": "36", "diagnosed_on": "2025-01-05"})
        dx = self.q("SELECT * FROM patient_diagnoses WHERE patient_id = ?", (pid,))
        self.assertEqual((dx["diagnosis"], dx["tooth"], dx["status"]), ("Irreversible pulpitis", "36", "active"))
        doc.post(f"/staff/patients/{pid}/diagnoses", data={"action": "resolve", "diagnosis_id": dx["id"]})
        self.assertEqual(self.q("SELECT status FROM patient_diagnoses WHERE id = ?", (dx["id"],))["status"], "resolved")
        self.assertIn("Irreversible pulpitis", doc.get(f"/staff/patients/{pid}?tab=diagnosis").data.decode())

    def test_split_payment_with_signature(self):
        from app.util import now_str
        _d, pid = self._patient_with_dentist()
        sjdm = self.branch("sjdm")
        inv = self.conn.insert("invoices", {"number": "TEST-PAY-1", "branch_id": sjdm, "patient_id": pid, "status": "issued",
                                            "issued_at": "2025-03-01", "subtotal_cents": 460000, "total_cents": 460000, "created_at": now_str()})
        admin = self.login("admin")
        page = admin.get(f"/staff/patients/{pid}?tab=billing").data.decode()
        self.assertIn(f'id="pay-{inv}"', page)
        # no signature and no reason: refused
        admin.post(f"/staff/invoices/{inv}/payments", data={"action": "multi", "method": ["cash"], "amount": ["100"]})
        self.assertIsNone(self.q("SELECT id FROM payments WHERE invoice_id = ?", (inv,)))
        # more than the balance: refused
        admin.post(f"/staff/invoices/{inv}/payments", data={"action": "multi", "method": ["cash", "gcash"], "amount": ["4000", "1000"],
                                                            "signature": "data:image/png;base64," + PNG})
        self.assertIsNone(self.q("SELECT id FROM payments WHERE invoice_id = ?", (inv,)))
        r = admin.post(f"/staff/invoices/{inv}/payments", data={"action": "multi", "method": ["cash", "gcash"], "amount": ["1000", "500.50"],
                                                                "reference": "OR-123", "received_at": "2025-03-02", "return_to": "patient",
                                                                "signature": "data:image/png;base64," + PNG})
        self.assertIn(f"/staff/patients/{pid}?tab=billing", r.headers["Location"])
        pays = self.conn.all("SELECT * FROM payments WHERE invoice_id = ? ORDER BY id", (inv,))
        self.assertEqual([(p["method"], p["amount_cents"]) for p in pays], [("cash", 100000), ("gcash", 50050)])
        self.assertEqual(pays[0]["signature_id"], pays[1]["signature_id"])
        sig = self.q("SELECT * FROM payment_signatures WHERE id = ?", (pays[0]["signature_id"],))
        self.assertTrue(sig["stored_name"].startswith("signatures/"))
        img = admin.get(f"/staff/invoices/{inv}/signatures/{sig['id']}")
        self.assertEqual((img.status_code, img.mimetype), (200, "image/png"))
        self.assertIn("no-store", img.headers["Cache-Control"])
        self.assertIn("Patient signature", admin.get(f"/staff/invoices/{inv}/print").data.decode())
        # a staff member from another branch can't see it
        self.assertEqual(self.login("staff.malolos").get(f"/staff/invoices/{inv}/signatures/{sig['id']}").status_code, 403)
        # not a PNG: refused
        admin.post(f"/staff/invoices/{inv}/payments", data={"action": "multi", "method": ["cash"], "amount": ["10"],
                                                            "signature": "data:image/png;base64," + base64.b64encode(b"<svg>" * 40).decode()})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM payments WHERE invoice_id = ?", (inv,))["n"], 2)
        # patient not present: allowed with a reason
        admin.post(f"/staff/invoices/{inv}/payments", data={"action": "multi", "method": ["bank_transfer"], "amount": ["100"],
                                                            "not_signed_reason": "Paid by parent online"})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM payments WHERE invoice_id = ?", (inv,))["n"], 3)
