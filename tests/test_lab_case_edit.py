"""Branch lab cases: edit items after sending, additional charges, and the lab invoice following the changes."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_lab_case_billing as base  # noqa: E402


class TestLabCaseEdit(base.TestLabCaseBilling):
    test_lab_sets_price_and_bills_branch = test_bill_by_case_with_units_extras_and_less = test_branch_cannot_bill = None

    def item(self, i, case_type, units, teeth, fee, item_id=""):
        return {"item_id": item_id, "case_type": case_type, "units": str(units), "teeth": teeth, "shade": "A2", "material": "",
                "material_new": "", "lab_fee": fee, "instructions": ""}

    def post_items(self, client, items, extras=(), instructions="Rush please"):
        data = {k: [it[k] for it in items] for k in items[0]}
        data.update({"x_desc": [e[0] for e in extras], "x_qty": [e[1] for e in extras], "x_price": [e[2] for e in extras],
                     "instructions_all": instructions})
        return client.post(f"/staff/lab/{self.case}/edit", data=data)

    def test_branch_edits_items_and_charges(self):
        d = self.login("dentist.malolos")
        self.assertIn("Edit items", d.get(f"/staff/lab/{self.case}").data.decode())
        self.assertEqual(d.get(f"/staff/lab/{self.case}/edit").status_code, 200)
        old = self.q("SELECT id FROM lab_case_items WHERE case_id = ?", (self.case,))["id"]
        r = self.post_items(d, [self.item(0, "Bridge", 3, "14-16", "3000", old), self.item(1, "Crown (PFM)", 1, "26", "2500")],
                            [("Rush fee", "1", "1000"), ("Model cast", "2", "250")])
        self.assertEqual(r.status_code, 302)
        items = self.conn.all("SELECT * FROM lab_case_items WHERE case_id = ? ORDER BY sort_order", (self.case,))
        self.assertEqual([(i["id"] == old, i["case_type"], i["units"], i["lab_fee_cents"]) for i in items],
                         [(True, "Bridge", 3, 300000), (False, "Crown (PFM)", 1, 250000)])
        c = self.q("SELECT * FROM lab_cases WHERE id = ?", (self.case,))
        self.assertEqual((c["units"], c["lab_fee_cents"], c["instructions"]), (4, 300000 + 250000 + 100000 + 50000, "Rush please"))
        self.assertIn(" + ", c["case_type"])
        page = d.get(f"/staff/lab/{self.case}").data.decode()
        for part in ("Rush fee", "Model cast", "₱7,000.00", "Additional charges"):
            self.assertIn(part, page)
        self.assertNotIn(f"Case #{self.case} · 4 ×", page)
        # remove one item and one charge again
        self.post_items(d, [self.item(0, "Bridge", 3, "14-16", "3000", old)], [("Rush fee", "1", "1000")])
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM lab_case_items WHERE case_id = ?", (self.case,))["n"], 1)
        self.assertEqual(self.q("SELECT lab_fee_cents FROM lab_cases WHERE id = ?", (self.case,))["lab_fee_cents"], 400000)

    def test_quick_charge_and_bill_includes_it(self):
        d = self.login("dentist.malolos")
        d.post(f"/staff/lab/{self.case}", data={"status": "sent", "lab_fee": "3500", "note": ""})
        d.post(f"/staff/lab/{self.case}", data={"action": "add_extra", "x_desc": "Rush fee", "x_qty": "1", "x_price": "500"})
        self.assertEqual(self.q("SELECT lab_fee_cents FROM lab_cases WHERE id = ?", (self.case,))["lab_fee_cents"], 400000)
        r = self.t.post(f"/staff/lab/cases/{self.case}/bill")
        iid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        lines = self.conn.all("SELECT description, amount_cents FROM lab_invoice_items WHERE invoice_id = ? ORDER BY id", (iid,))
        self.assertEqual([l["amount_cents"] for l in lines], [350000, 50000])
        self.assertIn("Rush fee", lines[1]["description"])
        self.assertEqual(self.q("SELECT total_cents FROM lab_invoices WHERE id = ?", (iid,))["total_cents"], 400000)
        # a change while the invoice is a draft updates it right away
        x = self.q("SELECT id FROM lab_case_extras WHERE case_id = ?", (self.case,))["id"]
        d.post(f"/staff/lab/{self.case}", data={"action": "remove_extra", "extra_id": x})
        self.assertEqual(self.q("SELECT total_cents FROM lab_invoices WHERE id = ?", (iid,))["total_cents"], 350000)
        # once issued: the case shows it's out of date, and the lab can update the invoice
        self.t.post(f"/staff/lab/invoices/{iid}", data={"action": "issue"})
        d.post(f"/staff/lab/{self.case}", data={"action": "add_extra", "x_desc": "Model cast", "x_qty": "1", "x_price": "300"})
        self.assertEqual(self.q("SELECT total_cents FROM lab_invoices WHERE id = ?", (iid,))["total_cents"], 350000)
        self.assertIn("doesn't match this case", self.t.get(f"/staff/lab/{self.case}").data.decode())
        self.assertEqual(d.post(f"/staff/lab/cases/{self.case}/refresh-invoice").status_code, 403)
        self.t.post(f"/staff/lab/cases/{self.case}/refresh-invoice")
        self.assertEqual(self.q("SELECT total_cents FROM lab_invoices WHERE id = ?", (iid,))["total_cents"], 380000)
        self.assertNotIn("doesn't match this case", self.t.get(f"/staff/lab/{self.case}").data.decode())

    def test_other_branch_cannot_edit(self):
        self.assertEqual(self.login("dentist.guiguinto").get(f"/staff/lab/{self.case}/edit").status_code, 403)


class TestCaseArch(__import__("test_app").Base):
    def test_upper_lower_on_branch_case(self):
        from app.util import now_str, today
        c = self.login("admin")
        lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        p = self.q("SELECT id FROM patients LIMIT 1")["id"]
        cid = self.conn.insert("lab_cases", {"lab_id": lab, "branch_id": self.branch("malolos"), "patient_id": p, "case_type": "Partial denture",
                                             "status": "sent", "sent_on": today().isoformat(), "created_at": now_str()})
        self.conn.insert("lab_case_items", {"case_id": cid, "case_type": "Partial denture", "units": 1, "sort_order": 0})
        it = self.q("SELECT id FROM lab_case_items WHERE case_id = ?", (cid,))
        page = c.get(f"/staff/lab/{cid}/edit").data.decode()
        self.assertIn("Upper / lower", page)
        self.assertIn('name="arch"', c.get(f"/staff/lab/new?patient_id={p}").data.decode())
        r = c.post(f"/staff/lab/{cid}/edit", data={"item_id": str(it["id"]), "case_type": "Partial denture", "units": "1", "arch": "lower",
                                                   "teeth": "", "shade": "A2", "material": "", "material_new": "", "lab_fee": "", "instructions": ""})
        self.assertEqual(r.status_code, 302, r.data[:500])
        self.assertEqual(self.q("SELECT arch FROM lab_case_items WHERE case_id = ?", (cid,))["arch"], "lower")
        self.assertIn("Lower", c.get(f"/staff/lab/{cid}").data.decode())
        # a value that isn't upper/lower/both is ignored
        c.post(f"/staff/lab/{cid}/edit", data={"item_id": str(it["id"]), "case_type": "Partial denture", "units": "1", "arch": "sideways",
                                               "teeth": "", "shade": "", "material": "", "material_new": "", "lab_fee": "", "instructions": ""})
        self.assertEqual(self.q("SELECT arch FROM lab_case_items WHERE case_id = ?", (cid,))["arch"], "")
