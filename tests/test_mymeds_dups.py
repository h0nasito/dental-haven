import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_app import Base  # noqa: E402


class TestMymedsDuplicates(Base):
    def test_find_and_remove_extra_copy(self):
        from app.util import now_str
        mal = self.branch("malolos")
        pid = self.conn.insert("patients", {"first_name": "Dupe", "last_name": "Demo", "chart_no": "DH-DUP1", "preferred_branch_id": mal,
                                            "created_at": now_str(), "updated_at": now_str()})
        inv = self.conn.insert("invoices", {"branch_id": mal, "patient_id": pid, "status": "issued", "number": "MM-DUP001", "issued_at": "2024-01-31 12:00:00",
                                            "subtotal_cents": 9200000, "discount_cents": 0, "tax_cents": 0, "total_cents": 9200000, "legacy": 1,
                                            "created_at": now_str()})
        ids = []
        for desc, amt in (("Orthodontic Treatment (demo)", 4500000), ("Orthodontic Treatment (demo)", 4500000), ("Oral Prophylaxis (demo)", 200000)):
            ids.append(self.conn.insert("invoice_items", {"invoice_id": inv, "description": desc, "qty": 1, "unit_price_cents": amt,
                                                          "discount_cents": 0, "amount_cents": amt, "done_on": "2024-01-31"}))
        self.conn.insert("payments", {"invoice_id": inv, "branch_id": mal, "kind": "payment", "amount_cents": 9200000, "method": "mymeds",
                                      "received_at": "2024-01-31 12:00:00", "status": "valid", "created_at": now_str()})
        a = self.login("admin")
        page = a.get("/staff/billing/mymeds-duplicates?q=dupe").data.decode()
        self.assertIn("Orthodontic Treatment (demo)", page)
        self.assertIn("₱45,000.00", page)
        a.post("/staff/billing/mymeds-duplicates", data={"item_id": str(ids[1])})
        inv_row = self.q("SELECT total_cents FROM invoices WHERE id = ?", (inv,))
        self.assertEqual(inv_row["total_cents"], 4700000)
        paid = self.conn.scalar("SELECT SUM(amount_cents) FROM payments WHERE invoice_id = ? AND status = 'valid'", (inv,))
        self.assertEqual(paid, 4700000)                                      # no false credit
        a.post("/staff/billing/mymeds-duplicates", data={"item_id": str(ids[0])})   # last copy stays
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM invoice_items WHERE invoice_id = ?", (inv,)), 2)
        self.assertEqual(self.login("dentist.malolos").get("/staff/billing/mymeds-duplicates").status_code, 403)


if __name__ == "__main__":
    unittest.main()
