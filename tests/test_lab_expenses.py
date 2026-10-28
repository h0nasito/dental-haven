"""Lab expenses: who can record them, voiding, and the net in the Lab financial report."""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import PW, Base  # noqa: E402

URL = "/staff/lab/expenses/"


class TestLabExpenses(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from app.auth import hash_password
        from app.util import now_str
        cls.lab = cls.conn.one("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        for name, role in (("labbill", "lab_billing_test"), ("labtech", "lab_tech_test")):
            uid = cls.conn.insert("users", {"email": f"{name}@demo.dentalhaven.test", "name": f"{name} (demo)", "password_hash": hash_password(PW),
                                            "role": "staff", "access_role": role, "active": 1, "must_change_password": 0, "created_at": now_str()})
            cls.conn.execute("INSERT INTO user_labs (user_id, lab_id) VALUES (?, ?)", (uid, cls.lab))
        for p in ("dashboard.view", "lab.works", "lab.billing"):
            cls.conn.execute("INSERT OR IGNORE INTO role_permissions (role, permission) VALUES ('lab_billing_test', ?)", (p,))
        for p in ("dashboard.view", "lab.works"):
            cls.conn.execute("INSERT OR IGNORE INTO role_permissions (role, permission) VALUES ('lab_tech_test', ?)", (p,))

    def add(self, c, **kw):
        from app.util import today
        data = {"expense_date": today().isoformat(), "category": "Lab materials & supplies", "item": "Zirconia disc", "qty": "2",
                "unit_price": "1,250", "amount": "", "paid_with": "cash", "payee": "Supplier Test", "reference": "OR-1"}
        data.update(kw)
        return c.post(URL, data=data)

    def test_record_list_void_and_net(self):
        from app.util import today
        c = self.login("labbill")
        self.assertEqual(self.add(c).status_code, 302)
        e = self.q("SELECT * FROM lab_expenses WHERE item = 'Zirconia disc' ORDER BY id DESC LIMIT 1")
        self.assertEqual((e["amount_cents"], e["lab_id"], e["status"], e["method"]), (250000, self.lab, "ok", "cash"))
        self.add(c, item="Courier to Malolos", category="Courier & delivery", qty="1", unit_price="", amount="150", paid_with="bank:BDO")
        self.add(c, item="Future", expense_date="2999-01-01")
        self.assertIsNone(self.q("SELECT id FROM lab_expenses WHERE item = 'Future'"))
        self.add(c, item="Bad bank", amount="10", unit_price="", paid_with="bank:Nope")
        self.assertIsNone(self.q("SELECT id FROM lab_expenses WHERE item = 'Bad bank'"))

        page = c.get(URL).data.decode()
        self.assertIn("Zirconia disc", page)
        self.assertIn("Courier &amp; delivery", page)

        rep = c.get("/staff/lab/financial").data.decode()
        self.assertIn("Lab expenses by category", rep)
        self.assertIn("Net (received − expenses)", rep)
        self.assertIn("₱150.00", rep)
        from app.views.lab_expenses import summary
        s = summary(self.conn, [self.lab], today().isoformat(), today().isoformat())
        self.assertEqual(s["by_source"]["Bank transfer – BDO"], 15000)

        # void: needs a reason, then it drops out of the totals
        c.post(f"/staff/lab/expenses/{e['id']}/void", data={"reason": ""})
        self.assertEqual(self.q("SELECT status FROM lab_expenses WHERE id = ?", (e["id"],))["status"], "ok")
        c.post(f"/staff/lab/expenses/{e['id']}/void", data={"reason": "Entered twice"})
        self.assertEqual(self.q("SELECT status FROM lab_expenses WHERE id = ?", (e["id"],))["status"], "void")
        s = summary(self.conn, [self.lab], today().isoformat(), today().isoformat())
        self.assertNotIn("Lab materials & supplies", dict(s["by_category"]))
        csv = c.get("/staff/lab/financial?format=csv").data.decode()
        self.assertIn("Less lab expenses", csv)
        self.assertIn("Courier & delivery", c.get(URL + "?format=csv").data.decode())
        self.assertTrue(self.q("SELECT id FROM audit_log WHERE action = 'lab_expense_voided'"))

    def test_receipt_upload_and_access(self):
        from test_landing import tiny_png
        c = self.login("labbill")
        c.post(URL, content_type="multipart/form-data", data={
            "category": "Electricity", "item": "Meralco", "amount": "3,000", "paid_with": "gcash",
            "receipt": (io.BytesIO(tiny_png()), "bill.png")})
        e = self.q("SELECT * FROM lab_expenses WHERE item = 'Meralco'")
        self.assertTrue(e["receipt_stored"])
        self.assertEqual(c.get(f"/staff/lab/expenses/{e['id']}/receipt").status_code, 200)
        self.assertEqual(self.login("labtech").get(f"/staff/lab/expenses/{e['id']}/receipt").status_code, 403)

    def test_only_lab_billing_staff(self):
        self.assertEqual(self.login("labtech").get(URL).status_code, 403)
        self.assertEqual(self.login("reception.malolos").get(URL).status_code, 403)
        self.assertEqual(self.login("admin").get(URL).status_code, 200)
        self.assertIn(b"Lab expenses", self.login("labbill").get("/staff/lab/financial").data)
