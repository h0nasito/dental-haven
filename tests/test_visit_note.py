"""New progress note: services per tooth, notes, recall, attachments, bill with discounts, patient signature, drafts."""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402
from test_patient_profile import PNG  # noqa: E402

JPG = b"\xff\xd8\xff\xe0" + b"0" * 200


class TestVisitNote(Base):
    def setUp(self):
        super().setUp()
        self.doc = self.q("SELECT id FROM users WHERE email = 'dentist.sjdm@demo.dentalhaven.test'")["id"]
        self.pid = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (self.doc,))["id"]
        self.sjdm = self.branch("sjdm")

    def _post(self, client, **extra):
        data = {"visit_date": "2025-06-03", "recall_date": "2025-07-03", "recall_reason": "Braces adjustment",
                "dentist_id": str(self.doc), "branch_id": str(self.sjdm), "body": "Adjusted wires. Patient tolerated well.",
                "line_service_id": ["", ""], "line_desc": ["Rebracket - Ordinary", "Braces Adjustment"], "line_tooth": ["35, 46", ""],
                "line_qty": ["", ""], "line_price": ["450", "1000"], "line_disc": ["10", ""], "bill_disc": "5", "create_bill": "1",
                "signature": "data:image/png;base64," + PNG, "action": "save"}
        data.update(extra)
        return client.post(f"/staff/patients/{self.pid}/visit-note", data=data, content_type="multipart/form-data")

    def test_save_note_creates_everything(self):
        admin = self.login("admin")
        page = admin.get(f"/staff/patients/{self.pid}?tab=notes").data.decode()
        self.assertIn('id="dlg-pn"', page)
        self.assertIn('id="pn-services"', page)
        r = self._post(admin, files=[(io.BytesIO(JPG), "xray.jpg")])
        self.assertEqual(r.status_code, 302)
        v = self.q("SELECT * FROM visit_notes WHERE patient_id = ? AND status = 'saved' ORDER BY id DESC", (self.pid,))
        self.assertTrue(v["signature_name"].startswith("signatures/"))
        procs = self.conn.all("SELECT * FROM procedures WHERE visit_note_id = ? ORDER BY id", (v["id"],))
        self.assertEqual([(p["description"], p["tooth"], p["performed_at"], p["performed_by"]) for p in procs],
                         [("Rebracket - Ordinary", "35, 46", "2025-06-03", self.doc), ("Braces Adjustment", "", "2025-06-03", self.doc)])
        self.assertIn("Adjusted wires", self.q("SELECT body FROM clinical_notes WHERE id = ?", (v["note_id"],))["body"])
        fu = self.q("SELECT * FROM follow_ups WHERE id = ?", (v["followup_id"],))
        self.assertEqual((fu["kind"], fu["due_at"][:10], fu["title"]), ("recall", "2025-07-03", "Recall: Braces adjustment"))
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM patient_documents WHERE visit_note_id = ?", (v["id"],))["n"], 1)
        # bill: 2 teeth x 450 = 900 - 10% = 810; + 1,000 = 1,810; bill discount 5% = 90.50 -> 1,719.50
        inv = self.q("SELECT * FROM invoices WHERE id = ?", (v["invoice_id"],))
        self.assertEqual((inv["status"], inv["subtotal_cents"], inv["discount_cents"], inv["total_cents"]), ("issued", 181000, 9050, 171950))
        items = self.conn.all("SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY id", (inv["id"],))
        self.assertEqual([(i["qty"], i["unit_price_cents"], i["discount_cents"], i["amount_cents"], i["tooth"], i["dentist_id"], i["done_on"])
                          for i in items], [(2, 45000, 9000, 81000, "35, 46", self.doc, "2025-06-03"),
                                            (1, 100000, 0, 100000, "", self.doc, "2025-06-03")])
        notes = admin.get(f"/staff/patients/{self.pid}?tab=notes").data.decode()
        for part in ("Signed by patient", "Recall Jul 3, 2025", "₱810.00", "1 file"):
            self.assertIn(part, notes)
        # the note text sits in the same row as the services (one row for the visit)
        row = notes.split("Jun 3, 2025")[1].split("</tr>")[0]
        self.assertIn("Adjusted wires", row)
        self.assertIn("Rebracket - Ordinary", row)
        sig = admin.get(f"/staff/patients/{self.pid}/visit-notes/{v['id']}/signature")
        self.assertEqual((sig.status_code, sig.mimetype), (200, "image/png"))

    def test_no_bill_without_billing_permission_and_dentist_is_self(self):
        doc = self.login("dentist.sjdm")
        self._post(doc, dentist_id="", signature="")
        v = self.q("SELECT * FROM visit_notes WHERE patient_id = ? AND status = 'saved' ORDER BY id DESC", (self.pid,))
        self.assertEqual(v["dentist_id"], self.doc)
        if not self.q("SELECT 1 AS x FROM role_permissions WHERE role = 'dentist' AND permission = 'billing.manage'"):
            self.assertIsNone(v["invoice_id"])
        self.assertEqual(v["signature_name"], "")

    def test_draft_then_errors_keep_input_then_save(self):
        admin = self.login("admin")
        self._post(admin, action="draft", signature="")
        d = self.q("SELECT * FROM visit_notes WHERE patient_id = ? AND status = 'draft' ORDER BY id DESC", (self.pid,))
        self.assertIsNotNone(d)
        self.assertIsNone(self.q("SELECT id FROM procedures WHERE visit_note_id = ?", (d["id"],)))
        self.assertIsNone(d["invoice_id"])
        page = admin.get(f"/staff/patients/{self.pid}?tab=notes&draft={d['id']}").data.decode()
        self.assertIn("data-autoopen", page)
        self.assertIn('value="Rebracket - Ordinary"', page)
        # a mistake (future date) keeps the input in the same draft
        r = self._post(admin, draft_id=str(d["id"]), visit_date="2099-01-01")
        self.assertIn(f"draft={d['id']}", r.headers["Location"])
        self.assertEqual(self.q("SELECT status FROM visit_notes WHERE id = ?", (d["id"],))["status"], "draft")
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM visit_notes WHERE patient_id = ? AND status = 'draft'", (self.pid,))["n"], 1)
        # bad discount
        self._post(admin, draft_id=str(d["id"]), line_disc=["abc", ""])
        self.assertEqual(self.q("SELECT status FROM visit_notes WHERE id = ?", (d["id"],))["status"], "draft")
        # now save the draft
        self._post(admin, draft_id=str(d["id"]))
        self.assertEqual(self.q("SELECT status FROM visit_notes WHERE id = ?", (d["id"],))["status"], "saved")
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM procedures WHERE visit_note_id = ?", (d["id"],))["n"], 2)

    def test_delete_draft_and_access(self):
        admin = self.login("admin")
        self._post(admin, action="draft", signature="")
        d = self.q("SELECT id FROM visit_notes WHERE patient_id = ? AND status = 'draft' ORDER BY id DESC", (self.pid,))["id"]
        front = self.login("staff.malolos")
        self.assertIn(front.post(f"/staff/patients/{self.pid}/visit-note", data={"action": "save"}).status_code, (403, 404))
        admin.post(f"/staff/patients/{self.pid}/visit-notes/{d}/delete")
        self.assertIsNone(self.q("SELECT id FROM visit_notes WHERE id = ?", (d,)))
