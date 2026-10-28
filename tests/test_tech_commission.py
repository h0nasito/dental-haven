"""Dental technicians: daily rate + commission. The commission is the technician's % of what the clinic pays for the works
and cases assigned to them, counted in the cutoff of the payment date. Older manual entries still count when delivered."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestTechCommission(Base):
    def test_commission_percent_of_payments(self):
        from app.util import now_str
        conn = self.conn
        admin = self.login("admin")
        lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        mal = self.branch("malolos")
        tech = conn.insert("employees", {"full_name": "Tech Commission (demo)", "position": "Technician", "employment_type": "regular",
                                         "primary_branch_id": mal, "active": 1, "created_at": now_str()})
        other = conn.insert("employees", {"full_name": "Other Tech (demo)", "position": "Dental Technician", "employment_type": "regular",
                                          "primary_branch_id": mal, "active": 1, "created_at": now_str()})
        conn.insert("compensation", {"employee_id": tech, "basis": "daily", "rate_cents": 60000, "effective_from": "2020-01-01", "created_at": now_str()})
        conn.insert("time_records", {"employee_id": tech, "branch_id": mal, "work_date": "2025-05-05", "time_in": "09:00", "time_out": "18:00",
                                     "status": "ok", "created_at": now_str()})
        # the % is set on the employee page
        admin.post(f"/staff/employees/{tech}", data={"action": "lab_commission_rate", "lab_commission": "10"})
        self.assertEqual(self.q("SELECT lab_commission_bp FROM employees WHERE id = ?", (tech,))["lab_commission_bp"], 1000)
        self.assertIn("Technician commission", admin.get(f"/staff/employees/{tech}").data.decode())

        client = conn.insert("lab_clients", {"lab_id": lab, "clinic_name": "Commission Test Clinic", "created_at": now_str()})

        def work(num, tech_id):
            return conn.insert("lab_works", {"number": num, "lab_id": lab, "client_id": client, "clinic_name": "Commission Test Clinic",
                                             "case_type": "Bridge", "units": 3, "status": "delivered", "received_on": "2025-05-01",
                                             "delivered_on": "2025-05-08", "technician_id": tech_id, "created_at": now_str(), "updated_at": now_str()})
        w_mine, w_other, w_manual = work("LW-T-1", None), work("LW-T-2", other), work("LW-T-3", tech)
        # assign the technician from the work page
        admin.post("/staff/lab/commission", data={"work_id": w_mine, "action": "assign", "technician_id": tech})
        self.assertEqual(self.q("SELECT technician_id FROM lab_works WHERE id = ?", (w_mine,))["technician_id"], tech)
        # one invoice: 6,000 for my work + 4,000 for the other technician's work, 1,000 invoice discount -> total 9,000
        inv = conn.insert("lab_invoices", {"number": "LI-T-1", "lab_id": lab, "client_id": client, "clinic_name": "Commission Test Clinic",
                                           "status": "issued", "issued_on": "2025-05-08", "subtotal_cents": 1000000, "discount_cents": 100000,
                                           "total_cents": 900000, "paid_cents": 450000, "created_at": now_str(), "updated_at": now_str()})
        for wid, amt in ((w_mine, 600000), (w_other, 400000)):
            conn.insert("lab_invoice_items", {"invoice_id": inv, "work_id": wid, "description": "Bridge", "qty": 1, "unit_price_cents": amt, "amount_cents": amt})
        conn.insert("lab_payments", {"invoice_id": inv, "receipt_no": "AR-T-1", "amount_cents": 450000, "method": "cash", "received_on": "2025-05-10",
                                     "status": "ok", "created_at": now_str()})
        conn.insert("lab_payments", {"invoice_id": inv, "receipt_no": "AR-T-2", "amount_cents": 100000, "method": "cash", "received_on": "2025-05-20",
                                     "status": "ok", "created_at": now_str()})   # next cutoff
        conn.insert("lab_payments", {"invoice_id": inv, "receipt_no": "AR-T-V", "amount_cents": 999900, "method": "cash", "received_on": "2025-05-11",
                                     "status": "void", "created_at": now_str()})  # voided: never counts
        # a work with an older manual entry: counted when delivered, no % on top
        conn.insert("lab_commissions", {"employee_id": tech, "work_id": w_manual, "amount_cents": 20000, "note": "old manual", "created_at": now_str()})
        inv2 = conn.insert("lab_invoices", {"number": "LI-T-2", "lab_id": lab, "client_id": client, "clinic_name": "Commission Test Clinic",
                                            "status": "issued", "subtotal_cents": 300000, "total_cents": 300000, "paid_cents": 300000,
                                            "created_at": now_str(), "updated_at": now_str()})
        conn.insert("lab_invoice_items", {"invoice_id": inv2, "work_id": w_manual, "description": "Bridge", "qty": 1, "unit_price_cents": 300000, "amount_cents": 300000})
        conn.insert("lab_payments", {"invoice_id": inv2, "receipt_no": "AR-T-3", "amount_cents": 300000, "method": "cash", "received_on": "2025-05-12",
                                     "status": "ok", "created_at": now_str()})

        r = admin.post("/staff/payroll", data={"start_date": "2025-05-01", "end_date": "2025-05-15", "branch_id": mal, "name": "May 1-15 TC"})
        pid = int(r.headers["Location"].rsplit("/", 1)[1])
        line = self.q("SELECT * FROM payroll_lines WHERE period_id = ? AND employee_id = ?", (pid, tech))
        # my share of the 4,500 payment = 4,500 x 6,000 / 10,000 = 2,700 -> 10% = 270; plus the manual 200
        self.assertEqual((line["commission_cents"], line["commission_items"]), (27000 + 20000, 2))
        self.assertEqual(line["estimate_cents"], 60000 + 47000)
        detail = admin.get(f"/staff/payroll/{pid}/technician/{tech}").data.decode()
        for part in ("LW-T-1", "10% of 2,700.00 paid", "AR-T-1", "old manual", "₱470.00"):
            self.assertIn(part, detail)
        page = admin.get(f"/staff/lab/works/{w_mine}").data.decode()
        self.assertIn("Dental technician", page)
        self.assertIn("₱270.00", page)
        # manual entries can't be added any more
        self.assertEqual(admin.post("/staff/lab/commission", data={"work_id": w_mine, "employee_id": tech, "amount": "100"}).status_code, 400)
