"""Dentist payroll: daily rate x days present + commission on completed procedures (billed - discount share - lab fee)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestDentistPay(Base):
    def test_daily_rate_plus_commission(self):
        from app.util import now_str
        conn = self.conn
        doc = self.q("SELECT id FROM users WHERE email = 'dentist.sjdm@demo.dentalhaven.test'")["id"]
        emp = self.q("SELECT * FROM employees WHERE user_id = ?", (doc,))
        sjdm = self.branch("sjdm")
        admin = self.login("admin")
        # rates via the employee page: 1,500/day + 40%; implants at 30%
        admin.post(f"/staff/employees/{emp['id']}", data={"action": "dentist_pay", "daily_rate": "1500", "commission": "40",
                                                            "effective_from": "2020-01-01"})
        implants = self.q("SELECT id FROM services WHERE slug = 'oral-surgery'")["id"]
        admin.post(f"/staff/employees/{emp['id']}", data={"action": "service_rate", "service_id": implants, "commission": "30"})
        self.assertEqual(self.q("SELECT commission_bp FROM dentist_pay_rates WHERE employee_id = ?", (emp["id"],))["commission_bp"], 4000)
        # an issued invoice in a quiet period: crown 20,000 with a 5,000 lab fee + implant 50,000; invoice discount 7,000 (10%)
        patient = self.q("SELECT id FROM patients LIMIT 1")["id"]
        day = "2031-03-10"
        inv = conn.insert("invoices", {"number": "TEST-DP-1", "branch_id": sjdm, "patient_id": patient, "status": "issued", "issued_at": day,
                                       "subtotal_cents": 7000000, "discount_cents": 700000, "total_cents": 6300000, "created_at": now_str()})
        conn.insert("invoice_items", {"invoice_id": inv, "description": "Zirconia crown", "qty": 1, "unit_price_cents": 2000000, "amount_cents": 2000000,
                                      "dentist_id": doc, "done_on": day, "lab_fee_cents": 500000})
        conn.insert("invoice_items", {"invoice_id": inv, "service_id": implants, "description": "Implant", "qty": 1, "unit_price_cents": 5000000,
                                      "amount_cents": 5000000, "dentist_id": doc, "done_on": day})
        # not counted: another dentist's line, and a line done outside the period
        conn.insert("invoice_items", {"invoice_id": inv, "description": "Cleaning", "qty": 1, "unit_price_cents": 0, "amount_cents": 0,
                                      "dentist_id": doc, "done_on": "2031-05-01"})
        # 3 days present
        conn.execute("DELETE FROM time_records WHERE employee_id = ? AND work_date BETWEEN '2031-03-01' AND '2031-03-15'", (emp["id"],))
        for d in ("2031-03-03", "2031-03-04", "2031-03-05"):
            conn.insert("time_records", {"employee_id": emp["id"], "branch_id": sjdm, "work_date": d, "time_in": "09:00", "time_out": "18:00",
                                         "status": "ok", "created_at": now_str()})
        r = admin.post("/staff/payroll", data={"start_date": "2031-03-01", "end_date": "2031-03-15", "branch_id": "", "name": "Test March"})
        pid = int(r.headers["Location"].rsplit("/", 1)[1])
        line = self.q("SELECT * FROM payroll_lines WHERE period_id = ? AND employee_id = ?", (pid, emp["id"]))
        # crown: 20,000 - 2,000 discount share - 5,000 lab = 13,000 x 40% = 5,200
        # implant: 50,000 - 5,000 discount share = 45,000 x 30% = 13,500
        self.assertEqual((line["kind"], line["days_present"], line["daily_pay_cents"]), ("dentist", 3, 450000))
        self.assertEqual((line["commission_base_cents"], line["commission_cents"], line["commission_items"]), (5800000, 1870000, 2))
        self.assertEqual(line["estimate_cents"], 450000 + 1870000)
        page = admin.get(f"/staff/payroll/{pid}").data.decode()
        self.assertIn("Dentists: daily rate + commission", page)
        detail = admin.get(f"/staff/payroll/{pid}/dentist/{emp['id']}").data.decode()
        for part in ("Zirconia crown", "-₱5,000.00", "₱13,000.00", "₱5,200.00", "30.0%", "₱18,700.00"):
            self.assertIn(part, detail)
        csv_text = admin.get(f"/staff/payroll/{pid}/export.csv").data.decode("utf-8-sig")
        self.assertIn("Commission (PHP)", csv_text)
        self.assertIn("18700.0", csv_text)

    def test_invoice_line_dentist_and_lab_fee(self):
        from app.util import now_str, today
        doc = self.q("SELECT id FROM users WHERE email = 'dentist.malolos@demo.dentalhaven.test'")["id"]
        mal = self.branch("malolos")
        patient = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 1", (mal,))["id"]
        lab = self.q("SELECT id FROM laboratories LIMIT 1")["id"]
        case = self.conn.insert("lab_cases", {"lab_id": lab, "branch_id": mal, "patient_id": patient, "dentist_id": doc, "case_type": "Bridge",
                                              "status": "delivered", "sent_on": today().isoformat(), "lab_fee_cents": 450000, "created_at": now_str()})
        inv = self.conn.insert("invoices", {"branch_id": mal, "patient_id": patient, "status": "draft", "created_at": now_str()})
        c = self.login("admin")
        c.post(f"/staff/invoices/{inv}/edit", data={"action": "add_item", "description": "Bridge (3 units)", "qty": "1", "unit_price": "30000",
                                                    "dentist_id": doc, "done_on": today().isoformat(), "lab_case_id": case})
        it = self.q("SELECT * FROM invoice_items WHERE invoice_id = ?", (inv,))
        self.assertEqual((it["dentist_id"], it["done_on"], it["lab_fee_cents"], it["lab_case_id"]), (doc, today().isoformat(), 450000, case))
        self.assertIn("lab fee ₱4,500.00", c.get(f"/staff/invoices/{inv}").data.decode())
        # still editable after issuing (payroll data), but not the amounts
        c.post(f"/staff/invoices/{inv}/edit", data={"action": "issue"})
        c.post(f"/staff/invoices/{inv}/edit", data={"action": "commission", "item_id": it["id"], "dentist_id": doc, "done_on": today().isoformat(),
                                                    "lab_case_id": "", "lab_fee": "4000"})
        self.assertEqual(self.q("SELECT lab_fee_cents FROM invoice_items WHERE id = ?", (it["id"],))["lab_fee_cents"], 400000)
        self.assertEqual(self.login("reception.malolos").post(f"/staff/invoices/{inv}/edit", data={"action": "commission", "item_id": it["id"],
                                                                                                    "lab_fee": "0"}).status_code, 403)
