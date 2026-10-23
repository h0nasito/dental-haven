"""Monthly bills: remove a recorded payment (draft), void a posted one, delete a bill that was never paid."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestBillRemove(Base):
    def test_remove_void_delete(self):
        from app.util import today
        a = self.login("admin")
        bid = self.branch("bocaue")
        mkey = today().strftime("%Y-%m")
        a.post("/staff/expenses/bills", data={"action": "add", "branch_id": bid, "category": "Rent", "item": "Water QT", "amount": "1500"})
        a.post("/staff/expenses/bills", data={"action": "add", "branch_id": bid, "category": "Rent", "item": "Mistake QT"})
        water = self.q("SELECT id FROM branch_bills WHERE item = 'Water QT'")["id"]
        oops = self.q("SELECT id FROM branch_bills WHERE item = 'Mistake QT'")["id"]
        a.post("/staff/expenses/bills", data={"action": "record", "bill_id": water, "month": mkey, "amount": "1500", "method": "cash"})
        e = self.q("SELECT * FROM expenses WHERE bill_id = ? AND bill_month = ?", (water, mkey))
        page = a.get(f"/staff/expenses/bills?month={mkey}").data.decode()
        self.assertIn("✕ Remove", page)
        # remove the draft -> back on the bills page, payment gone, can record again
        r = a.post(f"/staff/expenses/{e['id']}/delete", data={"next": f"/staff/expenses/bills?month={mkey}"})
        self.assertIn("/staff/expenses/bills", r.headers["Location"])
        self.assertIsNone(self.q("SELECT id FROM expenses WHERE id = ?", (e["id"],)))
        # record, post, then void with a reason
        a.post("/staff/expenses/bills", data={"action": "record", "bill_id": water, "month": mkey, "amount": "1500", "method": "cash"})
        e = self.q("SELECT * FROM expenses WHERE bill_id = ? AND bill_month = ? AND status = 'draft'", (water, mkey))
        a.post(f"/staff/expenses/{e['id']}/post", data={"next": "/staff/expenses/bills"})
        self.assertIn("✕ Void", a.get(f"/staff/expenses/bills?month={mkey}").data.decode())
        a.post(f"/staff/expenses/{e['id']}/void", data={"reason": "wrong amount", "next": "/staff/expenses/bills"})
        self.assertEqual(self.q("SELECT status FROM expenses WHERE id = ?", (e["id"],))["status"], "void")
        # a bill never paid can be deleted; the voided one could be deleted too now (no live payment)
        a.post("/staff/expenses/bills", data={"action": "delete_bill", "bill_id": oops, "month": mkey})
        self.assertIsNone(self.q("SELECT id FROM branch_bills WHERE id = ?", (oops,)))
        # with a live payment it stays
        a.post("/staff/expenses/bills", data={"action": "record", "bill_id": water, "month": mkey, "amount": "1500", "method": "cash"})
        a.post("/staff/expenses/bills", data={"action": "delete_bill", "bill_id": water, "month": mkey})
        self.assertIsNotNone(self.q("SELECT id FROM branch_bills WHERE id = ?", (water,)))
        # the "next" can't send you off-site
        e = self.q("SELECT * FROM expenses WHERE bill_id = ? AND status = 'draft'", (water,))
        r = a.post(f"/staff/expenses/{e['id']}/delete", data={"next": "https://example.com/"})
        self.assertTrue(r.headers["Location"].endswith("/staff/expenses/"))
