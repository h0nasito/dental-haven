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
        for part in ("Dental Treatment", "Plan Quotation", q["number"], "Zirconia crown", "₱31,000", "Not an official receipt", patient["last_name"],
                     "Valid until"):
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
        self.assertEqual(self.q("SELECT tooth FROM invoice_items WHERE invoice_id = ? ORDER BY id LIMIT 1", (inv_id,))["tooth"], "36")
        # patient page lists it
        self.assertIn(q["number"], s.get(f"/staff/patients/{patient['id']}?tab=billing").data.decode())

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

    def test_treatment_plan_with_options_and_freebies(self):
        c = self.login("admin")
        malolos = self.branch("malolos")
        r = c.post("/staff/quotes/new", data={"branch_id": malolos, "client_name": "Plan Demo Person", "valid_until": "2099-01-01"})
        qid = int(r.headers["Location"].rstrip("/").rsplit("/", 1)[1])
        def add(**kw):
            c.post(f"/staff/quotes/{qid}", data={"action": "add_item", **kw})
        add(plan="Plan A", section="Root Canal Therapy", description="Root Canal Therapy", tooth="21,22", qty="2", unit_price="12000", unit_label="canal")
        add(plan="Plan A", section="Root Canal Therapy", description="Extraction", tooth="15", qty="1", unit_price="950", unit_label="tooth",
            note="Need to heal for about a month before final restoration")
        add(plan="Plan A", section="Bridge", kind="option", description="Emax", tooth="12,11,21", qty="3", unit_price="30000", unit_label="unit",
            discount="20%")
        add(plan="Plan A", section="Bridge", kind="option", description="Zirconia", tooth="12,11,21", qty="3", unit_price="25000", unit_label="unit")
        add(plan="Plan A", kind="freebie", description="Temporary Crown/s", tooth="14 units", qty="14", unit_price="1000", unit_label="unit")
        add(plan="Plan A", kind="freebie", description="Night Guard", tooth="Upper only", qty="1", unit_price="10000", unit_label="arch")
        add(plan="Plan B", section="Extraction", description="Extraction", tooth="12,11,21,22", qty="4", unit_price="950", unit_label="tooth")
        c.post(f"/staff/quotes/{qid}", data={"action": "details", "recommended_plan": "Plan A", "prepared_by": "Dr. Demo Dentist",
                                             "valid_until": "2099-01-01"})
        q = self.q("SELECT * FROM quotations WHERE id = ?", (qid,))
        self.assertEqual(q["total_cents"], 2495000)   # Plan A treatments only: 24,000 + 950 (options and freebies not added)
        emax = self.q("SELECT * FROM quotation_items WHERE quotation_id = ? AND description = 'Emax'", (qid,))
        self.assertEqual((emax["discount_cents"], emax["amount_cents"]), (1800000, 7200000))
        pr = c.get(f"/staff/quotes/{qid}/print").data.decode()
        for part in ("PLAN A (RECOMMENDED)", "PLAN B", "A. Emax", "B. Zirconia", "Discounted Price", "90,000", "72,000", "12,000/canal",
                     "Note: Need to heal", "Freebies:", "TOTAL: 24,000", "Prepared by: Dr. Demo Dentist", "Plan Demo Person"):
            self.assertIn(part, pr)
        ed = c.get(f"/staff/quotes/{qid}").data.decode()
        self.assertIn("Recommended", ed)
        # move Plan B's line up, edit a line
        ext_b = self.q("SELECT id, seq FROM quotation_items WHERE quotation_id = ? AND plan = 'Plan B'", (qid,))
        c.post(f"/staff/quotes/{qid}", data={"action": "move", "item_id": ext_b["id"], "dir": "up"})
        self.assertLess(self.q("SELECT seq FROM quotation_items WHERE id = ?", (ext_b["id"],))["seq"], ext_b["seq"])
        c.post(f"/staff/quotes/{qid}", data={"action": "save_item", "item_id": ext_b["id"], "plan": "Plan B", "section": "Extraction",
                                             "kind": "item", "description": "Extraction", "tooth": "12,11,21,22", "qty": "4", "unit_price": "1000"})
        self.assertEqual(self.q("SELECT amount_cents FROM quotation_items WHERE id = ?", (ext_b["id"],))["amount_cents"], 400000)
        # accept -> invoice with the chosen lines (Plan A RCT + option Zirconia), freebies never billed
        c.post(f"/staff/quotes/{qid}", data={"action": "issue"})
        c.post(f"/staff/quotes/{qid}", data={"action": "accepted"})
        # walk-in quotes can't be billed; attach a patient to test the chosen-lines invoice
        pid = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (malolos,))["id"]
        self.conn.execute("UPDATE quotations SET patient_id = ? WHERE id = ?", (pid, qid))
        rct = self.q("SELECT id FROM quotation_items WHERE quotation_id = ? AND description = 'Root Canal Therapy'", (qid,))["id"]
        zr = self.q("SELECT id FROM quotation_items WHERE quotation_id = ? AND description = 'Zirconia'", (qid,))["id"]
        free = self.q("SELECT id FROM quotation_items WHERE quotation_id = ? AND kind = 'freebie' LIMIT 1", (qid,))["id"]
        c.post(f"/staff/quotes/{qid}", data={"action": "to_invoice", "item_ids": [str(rct), str(zr), str(free)]})
        inv = self.q("SELECT invoice_id FROM quotations WHERE id = ?", (qid,))["invoice_id"]
        lines = sorted(i["description"] for i in self.conn.all("SELECT description FROM invoice_items WHERE invoice_id = ?", (inv,)))
        self.assertEqual(lines, ["Root Canal Therapy", "Zirconia"])

    def test_custom_item_list(self):
        c = self.login("admin")
        self.assertGreaterEqual(self.q("SELECT COUNT(*) AS n FROM quote_presets")["n"], 18)
        page = c.get("/staff/quotes/items").data.decode()
        for part in ("Root Canal Therapy", "₱12,000.00/canal", "Tilite", "Water Floss", "Material options"):
            self.assertIn(part, page)
        # edit a price, add an item
        rct = self.q("SELECT * FROM quote_presets WHERE name = 'Root Canal Therapy'")
        c.post("/staff/quotes/items", data={"action": "save", "id": rct["id"], "name": "Root Canal Therapy", "price": "12500", "unit_label": "canal",
                                            "kind": "item", "section": "Root Canal Therapy", "active": "1"})
        self.assertEqual(self.q("SELECT unit_price_cents FROM quote_presets WHERE id = ?", (rct["id"],))["unit_price_cents"], 1250000)
        c.post("/staff/quotes/items", data={"action": "add", "name": "TEST Lithium Disilicate", "price": "28000", "unit_label": "unit", "kind": "option"})
        lid = self.q("SELECT * FROM quote_presets WHERE name = 'TEST Lithium Disilicate'")
        self.assertEqual(lid["kind"], "option")
        # use the list in a quotation: picking an item fills price, unit, type and section
        r = c.post("/staff/quotes/new", data={"branch_id": self.branch("malolos"), "client_name": "List Demo", "valid_until": "2099-01-01"})
        qid = int(r.headers["Location"].rstrip("/").rsplit("/", 1)[1])
        self.assertIn("TEST Lithium Disilicate", c.get(f"/staff/quotes/{qid}").data.decode())
        c.post(f"/staff/quotes/{qid}", data={"action": "add_item", "preset_id": rct["id"], "tooth": "36", "qty": "3", "unit_label": "canal",
                                             "section": "Root Canal Therapy"})
        it = self.q("SELECT * FROM quotation_items WHERE quotation_id = ?", (qid,))
        self.assertEqual((it["description"], it["unit_price_cents"], it["amount_cents"], it["kind"]), ("Root Canal Therapy", 1250000, 3750000, "item"))
        c.post(f"/staff/quotes/{qid}", data={"action": "add_item", "preset_id": lid["id"], "qty": "2"})
        opt = self.q("SELECT * FROM quotation_items WHERE quotation_id = ? AND description = 'TEST Lithium Disilicate'", (qid,))
        self.assertEqual((opt["kind"], opt["unit_price_cents"]), ("option", 2800000))
        # save a typed line to the list
        c.post(f"/staff/quotes/{qid}", data={"action": "add_item", "description": "TEST Gum Contouring", "unit_price": "8000", "unit_label": "arch",
                                             "kind": "item", "save_preset": "1"})
        self.assertIsNotNone(self.q("SELECT id FROM quote_presets WHERE name = 'TEST Gum Contouring' AND unit_label = 'arch'"))
        # remove from list
        c.post("/staff/quotes/items", data={"action": "delete", "id": lid["id"]})
        self.assertIsNone(self.q("SELECT id FROM quote_presets WHERE id = ?", (lid["id"],)))
        self.assertEqual(self.login("staff.bocaue").get("/staff/quotes/items").status_code in (200, 403), True)
        self.conn.execute("DELETE FROM quote_presets WHERE name LIKE 'TEST %'")
        self.conn.execute("UPDATE quote_presets SET unit_price_cents = 1200000 WHERE id = ?", (rct["id"],))

    def test_add_several_procedures_at_once(self):
        c = self.login("dentist.malolos")
        qid, _ = self._quote(c)
        fee = self.q("SELECT * FROM fee_schedule WHERE active = 1 ORDER BY id LIMIT 1")
        page = c.get(f"/staff/quotes/{qid}").data.decode()
        self.assertIn('name="m_proc"', page)
        self.assertIn("Add all", page)
        r = c.post(f"/staff/quotes/{qid}", data={
            "action": "add_many", "plan": "Plan A", "section": "Upper front",
            "m_proc": ["Root Canal Therapy", fee["name"], "Gum contouring", "", "Mystery work", "Emax"],
            "m_tooth": ["11", "12", "", "", "", "11,21"],
            "m_qty": ["1", "2", "1", "1", "1", "2"],
            "m_price": ["", "", "3,500", "", "", ""],
            "m_disc": ["10%", "", "", "", "", ""],
            "m_kind": ["item", "item", "item", "item", "item", "option"]}, follow_redirects=True)
        html = r.data.decode()
        self.assertIn("Added 4 procedure(s)", html)
        self.assertIn("Mystery work", html)  # skipped: no price
        items = self.conn.all("SELECT * FROM quotation_items WHERE quotation_id = ? ORDER BY seq", (qid,))
        self.assertEqual([i["description"] for i in items], ["Root Canal Therapy", fee["name"].title(), "Gum contouring", "Emax"])
        rct, fe, gum, emax = items
        self.assertEqual((rct["unit_price_cents"], rct["discount_cents"], rct["amount_cents"], rct["unit_label"], rct["tooth"]),
                         (1200000, 120000, 1080000, "canal", "11"))
        self.assertEqual((fe["unit_price_cents"], fe["qty"], fe["amount_cents"]), (fee["price_cents"], 2, 2 * fee["price_cents"]))
        self.assertEqual(gum["unit_price_cents"], 350000)
        self.assertEqual((emax["kind"], emax["unit_price_cents"]), ("option", 3000000))
        self.assertTrue(all(i["plan"] == "Plan A" and i["section"] == "Upper front" for i in items))
        q = self.q("SELECT * FROM quotations WHERE id = ?", (qid,))
        self.assertEqual(q["total_cents"], 1080000 + 2 * fee["price_cents"] + 350000)
        # nothing chosen
        r = c.post(f"/staff/quotes/{qid}", data={"action": "add_many", "m_proc": ["", ""]}, follow_redirects=True)
        self.assertIn("Choose or type at least one procedure", r.data.decode())
