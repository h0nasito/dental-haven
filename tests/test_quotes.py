"""Price quotations: create from the price list, finalise, print, accept, and turn into a draft invoice."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402


class TestQuotes(Base):
    def _quote(self, c, **kw):
        malolos = self.branch("malolos")
        patient = self.q("SELECT * FROM patients WHERE preferred_branch_id = ? LIMIT 1", (malolos,))
        d1 = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        r = c.post("/staff/quotes/new", data={"patient_id": patient["id"], "branch_id": malolos, "dentist_id": d1,
                                               "valid_until": "2099-01-01", **kw})
        self.assertEqual(r.status_code, 302, r.data[:500])
        qid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        return qid, patient

    def test_full_flow(self):
        c = self.login("dentist.malolos")
        qid, patient = self._quote(c)
        rct = self.q("SELECT * FROM price_items WHERE name = 'Root canal therapy: standard'")
        crown = self.q("SELECT * FROM price_items WHERE name = 'Zirconia crown / bridge'")
        # from the price list at its listed (sample) price
        c.post(f"/staff/quotes/{qid}", data={"action": "add_item", "price_item_id": rct["id"], "tooth": "36", "qty": "1"})
        # from the price list with the dentist's own price and a line discount
        c.post(f"/staff/quotes/{qid}", data={"action": "add_item", "price_item_id": crown["id"], "tooth": "36", "qty": "1",
                                             "unit_price": "18,000", "discount": "1000"})
        # a custom item
        c.post(f"/staff/quotes/{qid}", data={"action": "add_item", "description": "Night guard", "qty": "1", "unit_price": "5000"})
        items = self.conn.all("SELECT * FROM quotation_items WHERE quotation_id = ? ORDER BY seq", (qid,))
        self.assertEqual([i["description"] for i in items], ["Root canal therapy: standard", "Zirconia crown / bridge", "Night guard"])
        self.assertEqual([i["unit_price_cents"] for i in items], [950000, 1800000, 500000])
        self.assertEqual([i["sample_price"] for i in items], [0, 0, 0])
        self.assertEqual(items[1]["amount_cents"], 1700000)
        c.post(f"/staff/quotes/{qid}", data={"action": "details", "discount": "500", "notes": "Phase 1 first.", "valid_until": "2099-01-01"})
        q = self.q("SELECT * FROM quotations WHERE id = ?", (qid,))
        self.assertEqual((q["subtotal_cents"], q["discount_cents"], q["total_cents"]), (950000 + 1700000 + 500000, 50000, 3100000))
        self.assertNotIn("sample prices", c.get(f"/staff/quotes/{qid}").data.decode())
        # finalise → numbered, locked
        c.post(f"/staff/quotes/{qid}", data={"action": "issue"})
        q = self.q("SELECT * FROM quotations WHERE id = ?", (qid,))
        self.assertEqual(q["status"], "issued")
        self.assertRegex(q["number"], r"^QT-[A-Z]+-\d{4}-0001$")
        c.post(f"/staff/quotes/{qid}", data={"action": "add_item", "description": "Late add", "unit_price": "1"})
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM quotation_items WHERE quotation_id = ?", (qid,)), 3)
        pr = c.get(f"/staff/quotes/{qid}/print").data.decode()
        for part in ("Price quotation", q["number"], "Zirconia crown", "₱31,000.00", "not an official receipt", patient["last_name"], "Valid until"):
            self.assertIn(part, pr)
        # accepted → draft invoice (staff with billing rights)
        c.post(f"/staff/quotes/{qid}", data={"action": "accepted"})
        self.assertEqual(self.login("dentist.malolos").post(f"/staff/quotes/{qid}", data={"action": "to_invoice"}).status_code, 403)
        s = self.login("staff.malolos")
        r = s.post(f"/staff/quotes/{qid}", data={"action": "to_invoice"})
        self.assertEqual(r.status_code, 302)
        inv_id = self.q("SELECT invoice_id FROM quotations WHERE id = ?", (qid,))["invoice_id"]
        inv = self.q("SELECT * FROM invoices WHERE id = ?", (inv_id,))
        self.assertEqual((inv["status"], inv["total_cents"], inv["patient_id"]), ("draft", 3100000, patient["id"]))
        self.assertIn("(tooth 36)", self.q("SELECT description FROM invoice_items WHERE invoice_id = ? LIMIT 1", (inv_id,))["description"])
        # patient page lists it
        self.assertIn(q["number"], s.get(f"/staff/patients/{patient['id']}").data.decode())

    def test_non_patient_copy_delete_and_access(self):
        c = self.login("reception.malolos")
        malolos = self.branch("malolos")
        r = c.post("/staff/quotes/new", data={"branch_id": malolos, "client_name": "", "valid_until": "2099-01-01"})
        self.assertIn(b"Enter the name", r.data)
        r = c.post("/staff/quotes/new", data={"branch_id": malolos, "client_name": "Walk-in Demo", "client_contact": "0917 000 0000",
                                               "valid_until": "2099-01-01"})
        qid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        c.post(f"/staff/quotes/{qid}", data={"action": "add_item", "description": "Consultation", "unit_price": "500"})
        r = c.post(f"/staff/quotes/{qid}", data={"action": "duplicate"})
        copy_id = int(r.headers["Location"].rstrip("/").split("/")[-1])
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM quotation_items WHERE quotation_id = ?", (copy_id,)), 1)
        c.post(f"/staff/quotes/{copy_id}", data={"action": "delete"})
        self.assertIsNone(self.q("SELECT id FROM quotations WHERE id = ?", (copy_id,)))
        self.assertIn(b"Walk-in Demo", c.get("/staff/quotes").data)
        # another branch's staff can't open it
        self.assertEqual(self.login("staff.bocaue").get(f"/staff/quotes/{qid}").status_code, 403)
