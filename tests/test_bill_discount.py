"""Discount on an issued bill: amount or %, with a reason; never below what's paid (synthetic data only)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestIssuedDiscount(Base):
    def make_bill(self):
        from app.util import now_str
        b = self.branch("malolos")
        pid = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (b,))["id"]
        inv = self.conn.insert("invoices", {"branch_id": b, "patient_id": pid, "status": "issued", "number": f"T-{now_str()[-8:]}",
                                            "issued_at": "2026-10-01", "subtotal_cents": 200000, "discount_cents": 0, "tax_cents": 0,
                                            "total_cents": 200000, "created_at": now_str()})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Extraction", "qty": 1, "unit_price_cents": 200000,
                                           "discount_cents": 0, "amount_cents": 200000})
        return inv

    def test_discount_amount_percent_and_limits(self):
        inv = self.make_bill()
        a = self.login("admin")
        self.assertIn("Apply discount", a.get(f"/staff/invoices/{inv}").data.decode())
        a.post(f"/staff/invoices/{inv}/discount", data={"kind": "percent", "value": "20", "reason": "Senior citizen, ID checked"})
        r = self.q("SELECT total_cents, discount_cents, notes FROM invoices WHERE id = ?", (inv,))
        self.assertEqual((r["discount_cents"], r["total_cents"]), (40000, 160000))
        self.assertIn("Senior citizen", r["notes"])
        # reason needed
        a.post(f"/staff/invoices/{inv}/discount", data={"kind": "amount", "value": "100", "reason": ""})
        self.assertEqual(self.q("SELECT discount_cents FROM invoices WHERE id = ?", (inv,))["discount_cents"], 40000)
        # can't go below what's paid
        from app.util import now_str
        self.conn.insert("payments", {"invoice_id": inv, "branch_id": self.branch("malolos"), "kind": "payment", "amount_cents": 150000,
                                      "method": "cash", "received_at": now_str(), "status": "valid", "created_at": now_str()})
        a.post(f"/staff/invoices/{inv}/discount", data={"kind": "amount", "value": "1000", "reason": "promo"})
        self.assertEqual(self.q("SELECT total_cents FROM invoices WHERE id = ?", (inv,))["total_cents"], 160000)
        a.post(f"/staff/invoices/{inv}/discount", data={"kind": "amount", "value": "500", "reason": "promo"})
        self.assertEqual(self.q("SELECT total_cents FROM invoices WHERE id = ?", (inv,))["total_cents"], 150000)
        # a dentist (no bills.edit) can't
        self.assertEqual(self.login("dentist.malolos").post(f"/staff/invoices/{inv}/discount",
                                                            data={"kind": "amount", "value": "1", "reason": "x x"}).status_code, 403)


class TestDentistWhoDidWorkIsAssigned(Base):
    def test_bill_line_dentist_assigns_patient(self):
        from app.util import now_str
        uid = self.q("SELECT id FROM users WHERE email LIKE 'dentist.malolos@%'")["id"]
        b = self.branch("malolos")
        pid = self.conn.insert("patients", {"first_name": "Work", "last_name": "Assigntest", "chart_no": "DH-AS1", "preferred_branch_id": b,
                                            "created_at": now_str(), "updated_at": now_str()})
        self.assertIsNone(self.q("SELECT 1 AS x FROM patient_assignments WHERE patient_id = ?", (pid,)))
        inv = self.conn.insert("invoices", {"branch_id": b, "patient_id": pid, "status": "issued", "number": "AS-1", "issued_at": "2026-10-31",
                                            "subtotal_cents": 120000, "discount_cents": 0, "tax_cents": 0, "total_cents": 120000, "created_at": now_str()})
        line = self.conn.insert("invoice_items", {"invoice_id": inv, "description": "Restoration", "qty": 1, "unit_price_cents": 120000,
                                                  "discount_cents": 0, "amount_cents": 120000, "done_on": "2026-10-31"})
        self.assertIsNone(self.q("SELECT 1 AS x FROM patient_assignments WHERE patient_id = ?", (pid,)))
        self.conn.execute("UPDATE invoice_items SET dentist_id = ? WHERE id = ?", (uid, line))
        self.assertIsNotNone(self.q("SELECT 1 AS x FROM patient_assignments WHERE patient_id = ? AND dentist_id = ?", (pid, uid)))
        page = self.login("dentist.malolos").get("/staff/my-cases/?from=2026-10-01&to=2026-10-31").data.decode()
        self.assertIn("Assigntest", page)
        # staff (not dentists) on a line don't get assigned
        staff = self.q("SELECT id FROM users WHERE email LIKE 'staff.malolos@%'")["id"]
        self.conn.execute("UPDATE invoice_items SET dentist_id = ? WHERE id = ?", (staff, line))
        self.assertIsNone(self.q("SELECT 1 AS x FROM patient_assignments WHERE patient_id = ? AND dentist_id = ?", (pid, staff)))
