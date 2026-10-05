"""Deleting from the progress notes: procedure lines, billed items on a draft invoice, and written notes (super admin)."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402


class TestNoteDelete(Base):
    def setUp(self):
        super().setUp()
        from app.util import now_str
        self.pid = self.q("SELECT id FROM patients LIMIT 1")["id"]
        admin_id = self.q("SELECT id FROM users WHERE email = ?", ("admin" + DOMAIN,))["id"]
        self.nid = self.conn.insert("clinical_notes", {"patient_id": self.pid, "author_id": admin_id,
                                                        "body": f"Sample note to delete {id(self)}", "created_at": now_str(),
                                                        "legacy_key": f"test-note-{now_str()}-{id(self)}"})

    def test_super_admin_deletes_written_note_with_reason(self):
        a = self.login("admin")
        page = a.get(f"/staff/patients/{self.pid}?tab=notes").data.decode()
        self.assertIn(f"Delete note #{self.nid}", page)
        a.post(f"/staff/patients/{self.pid}/notes/{self.nid}/delete", data={"reason": ""})
        self.assertIsNone(self.q("SELECT deleted_at FROM clinical_notes WHERE id = ?", (self.nid,))["deleted_at"])
        a.post(f"/staff/patients/{self.pid}/notes/{self.nid}/delete", data={"reason": "Duplicate from import"})
        n = self.q("SELECT * FROM clinical_notes WHERE id = ?", (self.nid,))
        self.assertTrue(n["deleted_at"])
        self.assertEqual(n["deleted_reason"], "Duplicate from import")
        self.assertNotIn(f"Sample note to delete {id(self)}", a.get(f"/staff/patients/{self.pid}?tab=notes").data.decode())
        self.assertIsNotNone(self.q("SELECT id FROM audit_log WHERE action = 'progress_note_deleted'"))

    def test_dentist_cannot_delete_written_note(self):
        d = self.login("dentist.malolos")
        self.assertEqual(d.post(f"/staff/patients/{self.pid}/notes/{self.nid}/delete", data={"reason": "x y z"}).status_code, 403)

    def test_remove_billed_item_from_draft(self):
        from app.util import now_str
        a = self.login("admin")
        inv = self.conn.insert("invoices", {"patient_id": self.pid, "branch_id": self.branch("malolos"), "status": "draft",
                                            "subtotal_cents": 950000, "discount_cents": 0, "tax_cents": 0, "total_cents": 950000,
                                            "created_by": 1, "created_at": now_str()})
        item = self.conn.insert("invoice_items", {"invoice_id": inv, "description": "ORTHODONTIC TREATMENT (demo)", "qty": 1,
                                                  "unit_price_cents": 950000, "amount_cents": 950000, "done_on": date.today().isoformat()})
        page = a.get(f"/staff/patients/{self.pid}?tab=notes").data.decode()
        self.assertIn("from draft", page)
        r = a.post(f"/staff/invoices/{inv}/edit", data={"action": "remove_item", "item_id": item,
                                                                "next": f"/staff/patients/{self.pid}?tab=notes"})
        self.assertIn(f"/staff/patients/{self.pid}", r.headers["Location"])
        self.assertIsNone(self.q("SELECT id FROM invoice_items WHERE id = ?", (item,)))

    def test_voided_bill_leaves_no_empty_progress_row(self):
        from app.util import now_str
        a = self.login("admin")
        did = self.q("SELECT id FROM users WHERE role = 'dentist' LIMIT 1")["id"]
        inv = self.conn.insert("invoices", {"patient_id": self.pid, "branch_id": self.branch("malolos"), "status": "void",
                                            "number": f"VOID-{id(self)}", "created_by": 1, "created_at": now_str()})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Voided line (demo)", "qty": 1, "unit_price_cents": 100,
                                           "amount_cents": 100, "dentist_id": did, "done_on": "2026-01-02"})
        self.conn.insert("visit_notes", {"patient_id": self.pid, "branch_id": self.branch("malolos"), "dentist_id": did,
                                         "visit_date": "2026-01-02", "status": "saved", "invoice_id": inv,
                                         "created_by": 1, "created_at": now_str(), "updated_at": now_str()})
        page = a.get(f"/staff/patients/{self.pid}?tab=notes").data.decode()
        self.assertNotIn("Jan 2, 2026", page)
        self.assertNotIn("Voided line (demo)", page)
