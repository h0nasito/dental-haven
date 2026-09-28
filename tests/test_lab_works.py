"""Outside-clinic lab works, lab invoices/receipts and in-app notifications."""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import PW, Base  # noqa: E402


class TestLabWorks(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from app.auth import hash_password
        from app.util import now_str
        cls.lab = cls.conn.one("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        cls.techs = []
        for i in (1, 2):
            uid = cls.conn.insert("users", {"email": f"tech{i}@demo.dentalhaven.test", "name": f"Lab Tech {i} (demo)", "password_hash": hash_password(PW),
                                            "role": "staff", "active": 1, "must_change_password": 0, "created_at": now_str()})
            cls.conn.execute("INSERT INTO user_labs (user_id, lab_id) VALUES (?, ?)", (uid, cls.lab))
            cls.techs.append(uid)

    def tech(self, i=1):
        c = self.app.test_client()
        r = c.post("/staff/login", data={"email": f"tech{i}@demo.dentalhaven.test", "password": PW})
        self.assertEqual(r.status_code, 302)
        return c

    def grant(self, *perms):
        for p in perms:
            self.conn.execute("INSERT OR IGNORE INTO role_permissions (role, permission) VALUES ('staff', ?)", (p,))

    def revoke(self):
        self.conn.execute("DELETE FROM role_permissions WHERE role = 'staff' AND permission IN ('lab.works', 'lab.billing')")

    def new_work(self, c, **kw):
        from app.util import today
        data = {"lab_id": self.lab, "clinic_name": "Smile Bright Dental", "doctor": "Dr. Ana Reyes", "contact_number": "0917 000 0000",
                "patient_ref": "AB-12", "case_type": "Crown (zirconia / all-ceramic)", "units": "2", "arch": "upper", "teeth": "11, 21",
                "shade": "A2", "received_on": today().isoformat(), "due_on": (today() + timedelta(days=5)).isoformat(), "price": "3,500"}
        data.update(kw)
        r = c.post("/staff/lab/works/new", data=data)
        self.assertEqual(r.status_code, 302, r.data[:3000])
        return self.q("SELECT * FROM lab_works ORDER BY id DESC LIMIT 1")

    def test_access_needs_permission_and_lab(self):
        self.revoke()
        self.assertEqual(self.tech().get("/staff/lab/works").status_code, 403)
        self.grant("lab.works")
        try:
            self.assertEqual(self.tech().get("/staff/lab/works").status_code, 200)
            self.assertEqual(self.tech().get("/staff/lab/invoices").status_code, 403)          # billing is separate
            self.assertEqual(self.login("staff.malolos").get("/staff/lab/works").status_code, 403)  # has the permission but no lab
        finally:
            self.revoke()

    def test_work_status_and_notifications(self):
        self.grant("lab.works")
        try:
            c = self.tech(1)
            w = self.new_work(c)
            self.assertTrue(w["number"].startswith("LW-"))
            self.assertEqual((w["units"], w["arch"], w["price_cents"], w["status"]), (2, "upper", 350000, "received"))
            client = self.q("SELECT * FROM lab_clients WHERE id = ?", (w["client_id"],))
            self.assertEqual((client["clinic_name"], client["doctor"]), ("Smile Bright Dental", "Dr. Ana Reyes"))
            # the other tech is notified, not the one who saved it; no patient reference in the notice
            n = self.q("SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 1", (self.techs[1],))
            self.assertIn(w["number"], n["title"])
            self.assertNotIn("AB-12", n["title"] + n["body"])
            self.assertIsNone(self.q("SELECT id FROM notifications WHERE user_id = ? AND link = ?", (self.techs[0], f"/staff/lab/works/{w['id']}")))
            c.post(f"/staff/lab/works/{w['id']}", data={"status": "delivered", "delivered_on": w["received_on"], "note": "Picked up by rider"})
            w2 = self.q("SELECT * FROM lab_works WHERE id = ?", (w["id"],))
            self.assertEqual((w2["status"], w2["delivered_on"]), ("delivered", w["received_on"]))
            # the bell opens and marks it read
            c2 = self.tech(2)
            self.assertIn(w["number"], c2.get("/staff/notifications").data.decode())
            r = c2.post(f"/staff/notifications/{n['id']}/open")
            self.assertEqual(r.headers["Location"], f"/staff/lab/works/{w['id']}")
            self.assertIsNotNone(self.q("SELECT read_at FROM notifications WHERE id = ?", (n["id"],))["read_at"])
            # validation
            r = c.post("/staff/lab/works/new", data={"lab_id": self.lab, "clinic_name": "", "case_type": "Bridge", "units": "0", "received_on": "2099-01-01"})
            self.assertIn("Enter the dental clinic", r.data.decode())
        finally:
            self.revoke()

    def test_due_checks_run_once_a_day(self):
        from app import settings
        from app.notices import run_lab_due_checks
        from app.util import today
        self.grant("lab.works")
        try:
            w = self.new_work(self.tech(1), due_on=(today() + timedelta(days=1)).isoformat())
            settings.put("notify.lab_due_checked", "", None, self.conn)
            with self.app.test_request_context():
                run_lab_due_checks(self.conn)
                run_lab_due_checks(self.conn)
            self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM notifications WHERE title = ?", (f"Due tomorrow: {w['number']}",)), 2)  # one per tech
        finally:
            self.revoke()

    def test_invoice_discount_payment_receipt(self):
        self.grant("lab.works", "lab.billing")
        try:
            c = self.tech(1)
            w1 = self.new_work(c, clinic_name="Ngiti Dental Clinic", units="2", price="3500")
            w2 = self.new_work(c, clinic_name="Ngiti Dental Clinic", case_type="Complete denture", units="1", arch="both", price="")
            r = c.post("/staff/lab/invoices/new", data={"client": w1["client_id"], f"w_{w1['id']}": "1", f"w_{w2['id']}": "1"})
            inv = self.q("SELECT * FROM lab_invoices ORDER BY id DESC LIMIT 1")
            self.assertEqual(inv["subtotal_cents"], 700000)
            items = self.conn.all("SELECT * FROM lab_invoice_items WHERE invoice_id = ? ORDER BY id", (inv["id"],))
            base = f"/staff/lab/invoices/{inv['id']}"
            c.post(base, data={"action": "update_item", "item_id": items[1]["id"], "qty": "1", "unit_price": "12000", "item_discount": "500"})
            c.post(base, data={"action": "details", "discount": "10%", "discount_note": "Partner clinic", "due_on": "", "doctor": "Dr. Lim", "contact_number": ""})
            inv = self.q("SELECT * FROM lab_invoices WHERE id = ?", (inv["id"],))
            self.assertEqual((inv["subtotal_cents"], inv["discount_cents"], inv["total_cents"]), (1850000, 185000, 1665000))
            c.post(base, data={"action": "issue"})
            inv = self.q("SELECT * FROM lab_invoices WHERE id = ?", (inv["id"],))
            self.assertTrue(inv["number"].startswith("LI-"))
            r = c.post(base, data={"action": "pay", "amount": "20000", "method": "gcash", "received_on": inv["issued_on"]}, follow_redirects=True)
            self.assertIn("between", r.data.decode())  # more than the balance
            r = c.post(base, data={"action": "pay", "amount": "10000", "method": "gcash", "reference": "GC123", "received_on": inv["issued_on"]})
            p = self.q("SELECT * FROM lab_payments WHERE invoice_id = ?", (inv["id"],))
            self.assertTrue(p["receipt_no"].startswith("AR-"))
            self.assertEqual(self.q("SELECT paid_cents FROM lab_invoices WHERE id = ?", (inv["id"],))["paid_cents"], 1000000)
            receipt = c.get(f"/staff/lab/receipts/{p['id']}/print").data.decode()
            for part in ("Acknowledgment receipt", "not a BIR official receipt", "Ngiti Dental Clinic", "₱10,000.00", "₱6,650.00", "GC123"):
                self.assertIn(part, receipt)
            printed = c.get(f"{base}/print").data.decode()
            for part in ("Invoice", inv["number"], "Partner clinic", "-₱1,850.00", "₱16,650.00", "Digital Solutions Dental Laboratory"):
                self.assertIn(part, printed)
            # can't void an invoice with payments; void the payment first
            c.post(base, data={"action": "void", "reason": "Wrong clinic"})
            self.assertEqual(self.q("SELECT status FROM lab_invoices WHERE id = ?", (inv["id"],))["status"], "issued")
            c.post(base, data={"action": "void_payment", "payment_id": p["id"], "reason": "Bounced"})
            c.post(base, data={"action": "void", "reason": "Wrong clinic"})
            self.assertEqual(self.q("SELECT status FROM lab_invoices WHERE id = ?", (inv["id"],))["status"], "void")
            self.assertIsNone(self.q("SELECT invoice_id FROM lab_works WHERE id = ?", (w1["id"],))["invoice_id"])
        finally:
            self.revoke()
