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
            self.assertEqual((w["units"], w["arch"], w["price_cents"], w["status"]), (2, "upper", 350000, "accepted"))
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

    def test_several_cases_in_one_go(self):
        from app.util import today
        self.grant("lab.works")
        try:
            c = self.tech()
            page = c.get("/staff/lab/works/new").data.decode()
            self.assertIn("+ Add another case", page)
            before = self.q("SELECT COUNT(*) AS n FROM lab_works")["n"]
            r = c.post("/staff/lab/works/new", data={
                "lab_id": self.lab, "clinic_name": "Multi Case QT Dental", "doctor": "Dr. QT", "contact_number": "0917",
                "received_on": today().isoformat(), "due_on": "",
                "case_type": ["Bridge", "Complete denture", "Retainer"], "units": ["3", "1", "2"], "arch": ["", "upper", "both"],
                "teeth": ["14-16", "", ""], "shade": ["A2", "", ""], "material": ["Zirconia", "", ""], "price": ["3500", "2110", ""],
                "patient_ref": ["P1", "P2", "P3"], "instructions": ["", "", "Clear"]})
            self.assertEqual(r.status_code, 302)
            rows = self.conn.all("SELECT * FROM lab_works WHERE clinic_name = 'Multi Case QT Dental' ORDER BY id")
            self.assertEqual([(w["case_type"], w["units"], w["patient_ref"], w["price_cents"]) for w in rows],
                             [("Bridge", 3, "P1", 350000), ("Complete denture", 1, "P2", 211000), ("Retainer", 2, "P3", None)])
            self.assertEqual(len({w["client_id"] for w in rows}), 1)
            self.assertEqual(len({w["number"] for w in rows}), 3)
            self.assertIn("client=", r.headers["Location"])
            # one bad case: nothing is saved and the entries stay
            r = c.post("/staff/lab/works/new", data={
                "lab_id": self.lab, "clinic_name": "Multi Case QT Dental", "received_on": today().isoformat(),
                "case_type": ["Bridge", "Bridge"], "units": ["1", "0"], "arch": ["", ""], "teeth": ["11", "22"], "shade": ["", ""],
                "material": ["", ""], "price": ["", ""], "patient_ref": ["", ""], "instructions": ["", ""]})
            self.assertEqual(r.status_code, 200)
            self.assertIn("Enter the number of units", r.data.decode())
            self.assertIn('value="22"', r.data.decode())
            self.assertEqual(self.q("SELECT COUNT(*) AS n FROM lab_works")["n"], before + 3)
        finally:
            self.revoke()

    def test_additional_charges_billed_with_the_work(self):
        from app.util import today
        self.grant("lab.works", "lab.billing")
        try:
            c = self.tech()
            r = c.post("/staff/lab/works/new", data={
                "lab_id": self.lab, "clinic_name": "Extras QT Dental", "received_on": today().isoformat(),
                "case_type": ["Bridge", "Retainer"], "units": ["3", "1"], "arch": ["", ""], "teeth": ["", ""], "shade": ["", ""],
                "material": ["", ""], "price": ["3500", "1000"], "patient_ref": ["", ""], "instructions": ["", ""],
                "x_case": ["0", "0", "1"], "x_desc": ["3D printed cast", "Rush fee", "Model cast"], "x_qty": ["2", "1", "1"],
                "x_price": ["500", "1500", "500"]})
            self.assertEqual(r.status_code, 302)
            w1, w2 = self.conn.all("SELECT * FROM lab_works WHERE clinic_name = 'Extras QT Dental' ORDER BY id")
            ex1 = [(x["description"], x["qty"], x["unit_price_cents"]) for x in self.conn.all("SELECT * FROM lab_work_extras WHERE work_id = ? ORDER BY id", (w1["id"],))]
            self.assertEqual(ex1, [("3D printed cast", 2, 50000), ("Rush fee", 1, 150000)])
            self.assertEqual(self.q("SELECT COUNT(*) AS n FROM lab_work_extras WHERE work_id = ?", (w2["id"],))["n"], 1)
            # add one more on the work page, then bill: the work line + its charges
            c.post(f"/staff/lab/works/{w1['id']}", data={"action": "add_extra", "x_case": "0", "x_desc": "Individual tray", "x_qty": "1", "x_price": "300"})
            page = c.get(f"/staff/lab/works/{w1['id']}").data.decode()
            self.assertIn("Individual tray", page)
            self.assertIn("₱13,300.00", page)          # 3 x 3,500 + 2 x 500 + 1,500 + 300
            r = c.post(f"/staff/lab/works/{w1['id']}/bill")
            iid = int(r.headers["Location"].rstrip("/").split("/")[-1])
            items = [(i["description"], i["qty"], i["amount_cents"]) for i in self.conn.all("SELECT * FROM lab_invoice_items WHERE invoice_id = ? ORDER BY id", (iid,))]
            self.assertEqual(items[1:], [("3D printed cast", 2, 100000), ("Rush fee", 1, 150000), ("Individual tray", 1, 30000)])
            self.assertEqual(self.q("SELECT total_cents FROM lab_invoices WHERE id = ?", (iid,))["total_cents"], 1330000)
            # once billed, charges are changed on the invoice
            c.post(f"/staff/lab/works/{w1['id']}", data={"action": "add_extra", "x_case": "0", "x_desc": "Late", "x_qty": "1", "x_price": "1"})
            self.assertIsNone(self.q("SELECT id FROM lab_work_extras WHERE description = 'Late'"))
            # a charge without a price: nothing saved
            before = self.q("SELECT COUNT(*) AS n FROM lab_works")["n"]
            r = c.post("/staff/lab/works/new", data={"lab_id": self.lab, "clinic_name": "Extras QT Dental", "received_on": today().isoformat(),
                                                    "case_type": "Bridge", "units": "1", "x_case": "0", "x_desc": "Cast", "x_qty": "1", "x_price": ""})
            self.assertEqual(r.status_code, 200)
            self.assertIn("Enter the price for", r.data.decode())
            self.assertEqual(self.q("SELECT COUNT(*) AS n FROM lab_works")["n"], before)
        finally:
            self.revoke()

    def test_super_admin_removes_wrong_work(self):
        self.grant("lab.works")
        try:
            w = self.new_work(self.tech(), clinic_name="Remove QT Dental")
            self.conn.execute("INSERT INTO lab_work_extras (work_id, description, qty, unit_price_cents, created_at) VALUES (?, 'Cast', 1, 50000, '2026-01-01')", (w["id"],))
            self.assertEqual(self.tech().post(f"/staff/lab/works/{w['id']}/remove", data={"reason": "dup"}).status_code, 403)
            a = self.login("admin")
            a.post(f"/staff/lab/works/{w['id']}/remove", data={"reason": "Wrong clinic"})
            self.assertIsNone(self.q("SELECT id FROM lab_works WHERE id = ?", (w["id"],)))
            self.assertIsNone(self.q("SELECT id FROM lab_work_extras WHERE work_id = ?", (w["id"],)))
            self.assertIsNotNone(self.q("SELECT id FROM audit_log WHERE action = 'lab_work_removed' AND entity_id = ?", (w["id"],)))
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

    def test_collection_report(self):
        self.grant("lab.works", "lab.billing")
        try:
            c = self.tech(1)
            w = self.new_work(c, clinic_name="Collections Clinic", units="1", price="5000")
            c.post("/staff/lab/invoices/new", data={"client": w["client_id"], f"w_{w['id']}": "1"})
            inv = self.q("SELECT * FROM lab_invoices ORDER BY id DESC LIMIT 1")
            base = f"/staff/lab/invoices/{inv['id']}"
            c.post(base, data={"action": "issue"})
            day = self.q("SELECT issued_on FROM lab_invoices WHERE id = ?", (inv["id"],))["issued_on"]
            c.post(base, data={"action": "pay", "amount": "2000", "method": "cash", "received_on": day})
            c.post(base, data={"action": "pay", "amount": "1000", "method": "gcash", "reference": "GC9", "received_on": day})
            page = c.get("/staff/lab/collections", query_string={"from": day, "to": day, "client": w["client_id"]}).data.decode()
            for part in ("Lab collection report", "₱3,000.00", "Cash", "GCash", "Collections Clinic", "₱2,000.00"):
                self.assertIn(part, page)
            csv_text = c.get("/staff/lab/collections", query_string={"from": day, "to": day, "client": w["client_id"], "format": "csv"}).data.decode("utf-8-sig")
            self.assertIn("Receipt,Invoice", csv_text)
            self.assertIn("Total,3000.0", csv_text)
            self.revoke(); self.grant("lab.works")
            self.assertEqual(self.tech(1).get("/staff/lab/collections").status_code, 403)
        finally:
            self.revoke()


class TestOutsideWorkBilling(TestLabWorks):
    """Bill one outside clinic work like a branch case: units x price, extra lines and 'Less' lines; report split by type of clinic."""
    test_access_needs_permission_and_lab = test_work_status_and_notifications = None
    test_due_checks_run_once_a_day = test_invoice_discount_payment_receipt = test_collection_report = None

    def test_bill_one_work_with_extras_and_collect(self):
        self.grant("lab.works", "lab.billing")
        c = self.tech()
        wid = self.new_work(c, clinic_name="Smile Partner Clinic OWB", units="10", price="5500")["id"]
        self.assertIn("Bill this work", c.get(f"/staff/lab/works/{wid}").data.decode())
        r = c.post(f"/staff/lab/works/{wid}/bill")
        iid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        line = self.conn.one("SELECT * FROM lab_invoice_items WHERE invoice_id = ?", (iid,))
        self.assertEqual((line["work_id"], line["qty"], line["amount_cents"]), (wid, 10, 5500000))
        # posting again opens the same invoice
        self.assertTrue(c.post(f"/staff/lab/works/{wid}/bill").headers["Location"].endswith(f"/{iid}"))
        c.post(f"/staff/lab/invoices/{iid}", data={"action": "add_item", "for": f"w{wid}", "description": "Cast (upper and lower)", "qty": "2", "unit_price": "500"})
        c.post(f"/staff/lab/invoices/{iid}", data={"action": "add_item", "for": f"w{wid}", "description": "1 free unit", "qty": "1", "unit_price": "5500", "is_less": "1"})
        inv = self.conn.one("SELECT * FROM lab_invoices WHERE id = ?", (iid,))
        self.assertEqual(inv["total_cents"], 5050000)
        page = c.get(f"/staff/lab/invoices/{iid}").data.decode()
        self.assertIn("open work", page)
        # removing an extra line keeps the work on the invoice
        extra = self.conn.one("SELECT id FROM lab_invoice_items WHERE invoice_id = ? AND description LIKE 'Cast%'", (iid,))
        c.post(f"/staff/lab/invoices/{iid}", data={"action": "remove_item", "item_id": extra["id"]})
        self.assertEqual(self.conn.one("SELECT invoice_id FROM lab_works WHERE id = ?", (wid,))["invoice_id"], iid)
        c.post(f"/staff/lab/invoices/{iid}", data={"action": "issue"})
        total = self.conn.one("SELECT total_cents FROM lab_invoices WHERE id = ?", (iid,))["total_cents"]
        c.post(f"/staff/lab/invoices/{iid}", data={"action": "pay", "amount": f"{total / 100:.2f}", "method": "cash", "received_on": ""})
        # the collection report splits outside clinics and branches
        rep = c.get("/staff/lab/collections?kind=outside").data.decode()
        self.assertIn("Smile Partner Clinic OWB", rep)
        self.assertNotIn("Smile Partner Clinic OWB", c.get("/staff/lab/collections?kind=branch").data.decode())
        self.assertIn("By type of clinic", c.get("/staff/lab/collections").data.decode())
        csv = c.get("/staff/lab/collections?format=csv&kind=outside").data.decode()
        self.assertIn("Outside clinic", csv)
        self.assertIn("Smile Partner Clinic OWB", c.get("/staff/lab/invoices?show=all&kind=outside").data.decode())
        self.assertNotIn("Smile Partner Clinic OWB", c.get("/staff/lab/invoices?show=all&kind=branch").data.decode())


class TestLabFinancial(TestLabWorks):
    test_access_needs_permission_and_lab = test_work_status_and_notifications = None
    test_due_checks_run_once_a_day = test_invoice_discount_payment_receipt = test_collection_report = None

    def test_lab_financial_report(self):
        self.grant("lab.works", "lab.billing")
        c = self.tech()
        wid = self.new_work(c, clinic_name="Finance Test Clinic LFR", units="2", price="1000")["id"]
        iid = int(c.post(f"/staff/lab/works/{wid}/bill").headers["Location"].rstrip("/").split("/")[-1])
        c.post(f"/staff/lab/invoices/{iid}", data={"action": "issue"})
        page = c.get(f"/staff/lab/invoices/{iid}").data.decode()
        self.assertIn('value="bank:BDO"', page)
        c.post(f"/staff/lab/invoices/{iid}", data={"action": "pay", "amount": "500", "method": "bank", "received_on": ""})   # no bank: refused
        self.assertEqual(self.conn.one("SELECT COUNT(*) AS n FROM lab_payments WHERE invoice_id = ?", (iid,))["n"], 0)
        c.post(f"/staff/lab/invoices/{iid}", data={"action": "pay", "amount": "1500", "method": "bank:BPI", "received_on": ""})
        c.post(f"/staff/lab/invoices/{iid}", data={"action": "pay", "amount": "500", "method": "gcash", "received_on": ""})
        rep = c.get("/staff/lab/financial").data.decode()
        self.assertIn("Bank transfer – BPI", rep)
        self.assertIn("₱1,500.00", rep)
        from app import finance_report
        from app.util import today
        r = finance_report.lab_build(self.conn, [self.lab], today().isoformat(), today().isoformat())
        acc = {a["name"]: a["total"] for a in r["accounts"]}
        self.assertGreaterEqual(acc["BPI"], 150000)
        self.assertIn("Bank transfer – BPI", c.get("/staff/lab/financial?format=csv").data.decode())
