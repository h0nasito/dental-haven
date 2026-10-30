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

    def test_cancel_visit_hides_it_and_cancels_recall(self):
        admin = self.login("admin")
        self._post(admin, recall_date="2025-08-09", create_bill="", visit_date="2025-06-09")
        v = self.q("SELECT * FROM visit_notes WHERE patient_id = ? AND status = 'saved' AND visit_date = '2025-06-09'", (self.pid,))
        self.assertIsNotNone(v)
        page = admin.get(f"/staff/patients/{self.pid}?tab=notes").data.decode()
        self.assertIn("Recall Aug 9, 2025", page)
        self.assertIn("Cancel visit", page)
        admin.post(f"/staff/patients/{self.pid}/visit-notes/{v['id']}/cancel", data={"reason": ""})          # needs a reason
        self.assertIsNone(self.q("SELECT cancelled_at FROM visit_notes WHERE id = ?", (v["id"],))["cancelled_at"])
        admin.post(f"/staff/patients/{self.pid}/visit-notes/{v['id']}/cancel", data={"reason": "Entered by mistake"})
        v2 = self.q("SELECT * FROM visit_notes WHERE id = ?", (v["id"],))
        self.assertIsNotNone(v2["cancelled_at"])
        self.assertTrue(v2["signature_name"])                                        # the signed record is kept
        self.assertEqual(self.q("SELECT status FROM follow_ups WHERE id = ?", (v["followup_id"],))["status"], "cancelled")
        self.assertNotIn("Recall Aug 9, 2025", admin.get(f"/staff/patients/{self.pid}?tab=notes").data.decode())
        # a receptionist can't
        self.assertEqual(self.login("reception.sjdm").post(f"/staff/patients/{self.pid}/visit-notes/{v['id']}/cancel",
                                                            data={"reason": "x y z"}).status_code, 403)

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


class TestNoteToBill(TestVisitNote):
    """A dentist saves services; the cashier creates the bill from the note."""

    def test_dentist_note_waits_for_cashier(self):
        from app.util import today
        t = today().isoformat()
        doc = self.login("dentist.sjdm")
        r = self._post(doc, visit_date=t, recall_date="", signature="", create_bill="1")
        self.assertEqual(r.status_code, 302)
        v = self.q("SELECT * FROM visit_notes WHERE patient_id = ? AND status = 'saved' ORDER BY id DESC", (self.pid,))
        self.assertIsNone(v["invoice_id"])
        self.assertEqual(v["create_bill"], 1)
        # billing staff of the branch are notified (no patient name in the notification)
        n = self.q("SELECT * FROM notifications WHERE kind = 'to_bill' ORDER BY id DESC LIMIT 1")
        self.assertIn("Progress note to bill", n["title"])
        self.assertNotIn(self.q("SELECT last_name FROM patients WHERE id = ?", (self.pid,))["last_name"], n["title"] + n["body"])
        admin = self.login("admin")
        page = admin.get(f"/staff/patients/{self.pid}?tab=billing").data.decode()
        self.assertIn("Progress notes waiting for a bill", page)
        self.assertIn("₱1,719.50", page)
        self.assertIn("Progress notes waiting for a bill", admin.get("/staff/invoices").data.decode())
        r = admin.post(f"/staff/patients/{self.pid}/visit-note/{v['id']}/bill", data={})
        self.assertEqual(r.status_code, 302)
        v = self.q("SELECT * FROM visit_notes WHERE id = ?", (v["id"],))
        inv = self.q("SELECT * FROM invoices WHERE id = ?", (v["invoice_id"],))
        self.assertEqual((inv["status"], inv["subtotal_cents"], inv["discount_cents"], inv["total_cents"]), ("issued", 181000, 9050, 171950))
        items = self.conn.all("SELECT qty, tooth, dentist_id, done_on FROM invoice_items WHERE invoice_id = ? ORDER BY id", (inv["id"],))
        self.assertEqual([(i["qty"], i["tooth"], i["dentist_id"], i["done_on"]) for i in items], [(2, "35, 46", self.doc, t), (1, "", self.doc, t)])
        from app.views.patients import notes_to_bill
        with self.app.test_request_context():
            from flask import g
            from app.db import get_db
            waiting = notes_to_bill(get_db(), [self.sjdm], self.pid)
        self.assertFalse([w for w in waiting if w["kind"] == "note" and w["id"] == v["id"]])
        # twice: no second bill
        admin.post(f"/staff/patients/{self.pid}/visit-note/{v['id']}/bill", data={})
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM visit_notes WHERE invoice_id = ?", (inv["id"],)), 1)
        # a dentist can't create bills
        self.assertEqual(doc.post(f"/staff/patients/{self.pid}/visit-note/{v['id']}/bill", data={}).status_code, 403)

    def test_plan_and_recorded_procedures_wait_too(self):
        """Generate progress note (treatment plan) and Record procedure by a dentist also reach the cashier."""
        from app.util import now_str, today
        doc = self.login("dentist.sjdm")
        self.conn.execute("UPDATE patients SET preferred_branch_id = ? WHERE id = ?", (self.sjdm, self.pid))
        plan = self.conn.insert("treatment_plans", {"patient_id": self.pid, "title": "Plan T2B", "status": "accepted", "created_at": now_str(),
                                                    "updated_at": now_str()})
        item = self.conn.insert("treatment_plan_items", {"plan_id": plan, "description": "Composite filling T2B", "tooth": "16",
                                                         "estimate_cents": 150000, "status": "pending", "seq": 1})
        doc.post(f"/staff/patients/{self.pid}/plans", data={"action": "generate", "plan_id": plan, "item_id": item})
        pr = self.q("SELECT * FROM procedures WHERE description = 'Composite filling T2B'")
        self.assertIsNotNone(pr, "plan item was not generated")
        self.assertEqual(pr["price_cents"], 150000)
        from app.views.patients import notes_to_bill
        with self.app.test_request_context():
            from app.db import get_db
            waiting = [w for w in notes_to_bill(get_db(), [self.sjdm], self.pid) if w["kind"] == "proc" and pr["id"] in w["proc_ids"]]
        self.assertEqual(len(waiting), 1)
        admin = self.login("admin")
        r = admin.post(f"/staff/patients/{self.pid}/procedures/bill", data={"ids": ",".join(str(i) for i in waiting[0]["proc_ids"])})
        self.assertEqual(r.status_code, 302)
        inv_id = self.q("SELECT invoice_id FROM procedures WHERE id = ?", (pr["id"],))["invoice_id"]
        self.assertTrue(inv_id)
        lines = self.conn.all("SELECT description, amount_cents FROM invoice_items WHERE invoice_id = ?", (inv_id,))
        self.assertIn(("Composite filling T2B", 150000), [(l["description"], l["amount_cents"]) for l in lines])

    def test_no_bill_needed(self):
        from app.util import today
        doc = self.login("dentist.sjdm")
        self._post(doc, visit_date=today().isoformat(), recall_date="", signature="")
        v = self.q("SELECT * FROM visit_notes WHERE patient_id = ? AND status = 'saved' ORDER BY id DESC", (self.pid,))
        admin = self.login("admin")
        admin.post(f"/staff/patients/{self.pid}/visit-note/{v['id']}/bill", data={"action": "skip"})
        self.assertTrue(self.q("SELECT bill_skipped_at FROM visit_notes WHERE id = ?", (v["id"],))["bill_skipped_at"])
        self.assertIsNone(self.q("SELECT invoice_id FROM visit_notes WHERE id = ?", (v["id"],))["invoice_id"])


for _n in [n for n in dir(TestVisitNote) if n.startswith("test_")]:
    setattr(TestNoteToBill, _n, None)


class TestEnteredBy(TestVisitNote):
    def test_shows_who_entered_the_note(self):
        admin = self.login("admin")
        self._post(admin, signature="")
        notes = admin.get(f"/staff/patients/{self.pid}?tab=notes").data.decode()
        row = notes.split("Jun 3, 2025")[1].split("</td>")[0]
        self.assertIn("Entered by Demo Super Admin", row)
        # the dentist's own note doesn't repeat their name
        doc = self.login("dentist.sjdm")
        self._post(doc, visit_date="2025-06-04", recall_date="", signature="")
        notes = doc.get(f"/staff/patients/{self.pid}?tab=notes").data.decode()
        self.assertNotIn("Entered by", notes.split("Jun 4, 2025")[1].split("</td>")[0])


for _n in [n for n in dir(TestVisitNote) if n.startswith("test_")]:
    setattr(TestEnteredBy, _n, None)


class TestVisitNoteXray(Base):
    """X-rays added in a progress note: kept in the dentist's record, paid in the X-ray section (not the patient's bill)."""
    _post = TestVisitNote._post

    def setUp(self):
        self.doc = self.q("SELECT id FROM users WHERE email = 'dentist.sjdm@demo.dentalhaven.test'")["id"]
        self.pid = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (self.doc,))["id"]
        self.sjdm = self.branch("sjdm")

    def test_xray_in_progress_note_goes_to_xray_section(self):
        from app.views.patients import notes_to_bill
        doc = self.login("dentist.sjdm")
        invs = self.conn.scalar("SELECT COUNT(*) FROM invoices WHERE patient_id = ?", (self.pid,))
        from datetime import date
        r = self._post(doc, dentist_id="", signature="", recall_date="", visit_date=date.today().isoformat(), line_service_id=["", "", ""],
                       line_desc=["PANORAMIC XRAY", "Xray - Periapical", "Oral prophylaxis (Mild)"], line_tooth=["", "36", ""],
                       line_qty=["", "", ""], line_price=["1000", "300", "800"], line_disc=["", "", ""], bill_disc="")
        self.assertEqual(r.status_code, 302)
        v = self.q("SELECT * FROM visit_notes WHERE patient_id = ? AND status = 'saved' ORDER BY id DESC", (self.pid,))
        x = self.q("SELECT * FROM xrays WHERE visit_note_id = ?", (v["id"],))
        self.assertIsNotNone(x)
        self.assertEqual((x["total_cents"], x["requested_by"], x["patient_id"]), (100000, self.doc, self.pid))
        self.assertEqual([i["description"] for i in self.conn.all("SELECT description FROM xray_items WHERE xray_id = ?", (x["id"],))],
                         ["Panoramic"])
        procs = self.conn.all("SELECT description, xray_id FROM procedures WHERE visit_note_id = ? ORDER BY id", (v["id"],))
        self.assertEqual([(p["description"], bool(p["xray_id"])) for p in procs],
                         [("PANORAMIC XRAY", True), ("Xray - Periapical", False), ("Oral prophylaxis (Mild)", False)])
        # the cashier's "to bill" has the periapical and prophylaxis only
        with self.app.test_request_context():
            entry = next(e for e in notes_to_bill(self.conn, [self.sjdm], self.pid) if e["kind"] == "note" and e["id"] == v["id"])
        self.assertEqual(entry["services"], "Xray - Periapical, Oral prophylaxis (Mild)")
        self.assertEqual(entry["estimate"], 110000)
        admin = self.login("admin")
        admin.post(f"/staff/patients/{self.pid}/visit-note/{v['id']}/bill", data={"action": "create"})
        inv = self.q("SELECT * FROM invoices WHERE patient_id = ? ORDER BY id DESC", (self.pid,))
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM invoices WHERE patient_id = ?", (self.pid,)), invs + 1)
        self.assertEqual(inv["total_cents"], 110000)
        # the progress note links to the X-ray record
        notes = admin.get(f"/staff/patients/{self.pid}?tab=notes").data.decode()
        self.assertIn(f"X-ray {x['number']}", notes)
        # cancelling the visit voids the unpaid X-ray
        admin.post(f"/staff/patients/{self.pid}/visit-notes/{v['id']}/cancel", data={"reason": "wrong patient"})
        self.assertEqual(self.q("SELECT status FROM xrays WHERE id = ?", (x["id"],))["status"], "void")


class TestProgressNotePrice(Base):
    """Changing a saved progress note's price changes its bill, as long as the bill has no payment."""
    _post = TestVisitNote._post

    def setUp(self):
        self.doc = self.q("SELECT id FROM users WHERE email = 'dentist.sjdm@demo.dentalhaven.test'")["id"]
        self.pid = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (self.doc,))["id"]
        self.sjdm = self.branch("sjdm")

    def test_change_price_until_paid(self):
        from app.util import now_str
        admin = self.login("admin")
        self._post(admin, signature="", recall_date="", line_service_id=[""], line_desc=["Pasta (demo price test)"], line_tooth=["16"],
                   line_qty=[""], line_price=["1000"], line_disc=[""], bill_disc="")
        v = self.q("SELECT * FROM visit_notes WHERE patient_id = ? AND status = 'saved' ORDER BY id DESC", (self.pid,))
        pr = self.q("SELECT * FROM procedures WHERE visit_note_id = ?", (v["id"],))
        self.assertIn(f'id="epr{pr["id"]}"', admin.get(f"/staff/patients/{self.pid}?tab=notes").data.decode())
        admin.post(f"/staff/patients/{self.pid}/procedures/{pr['id']}", data={"action": "edit", "description": pr["description"], "tooth": "16",
                                                                             "performed_at": pr["performed_at"], "price": "1500", "price_was": "1000.00"})
        inv = self.q("SELECT * FROM invoices WHERE id = ?", (v["invoice_id"],))
        self.assertEqual(inv["total_cents"], 150000)
        # once paid, the price stays
        self.conn.insert("payments", {"invoice_id": inv["id"], "branch_id": self.sjdm, "kind": "payment", "amount_cents": 50000, "method": "cash",
                                      "received_at": now_str(), "status": "valid", "created_at": now_str()})
        r = admin.post(f"/staff/patients/{self.pid}/procedures/{pr['id']}", data={"action": "edit", "description": pr["description"], "tooth": "16",
                                                                                 "performed_at": pr["performed_at"], "price": "900", "price_was": "1500.00"},
                       follow_redirects=True)
        self.assertIn("already has a payment", r.data.decode())
        self.assertEqual(self.q("SELECT total_cents FROM invoices WHERE id = ?", (inv["id"],))["total_cents"], 150000)
