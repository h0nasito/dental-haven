"""Dental technicians: daily rate + manual commission, counted when the work leaves the lab (delivered)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestTechCommission(Base):
    def test_commission_counts_when_delivered(self):
        from app.util import now_str
        conn = self.conn
        admin = self.login("admin")
        lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        mal = self.branch("malolos")
        tech = conn.insert("employees", {"full_name": "Tech Commission (demo)", "position": "Technician", "employment_type": "regular",
                                         "primary_branch_id": mal, "active": 1, "created_at": now_str()})
        conn.insert("compensation", {"employee_id": tech, "basis": "daily", "rate_cents": 60000, "effective_from": "2020-01-01", "created_at": now_str()})
        conn.insert("time_records", {"employee_id": tech, "branch_id": mal, "work_date": "2025-05-05", "time_in": "09:00", "time_out": "18:00",
                                     "status": "ok", "created_at": now_str()})
        client = conn.insert("lab_clients", {"lab_id": lab, "clinic_name": "Commission Test Clinic", "created_at": now_str()})
        def work(status, delivered):
            return conn.insert("lab_works", {"number": f"LW-T-{status}-{delivered}", "lab_id": lab, "client_id": client, "clinic_name": "Commission Test Clinic",
                                             "case_type": "Bridge", "units": 3, "status": status, "received_on": "2025-05-01", "delivered_on": delivered,
                                             "created_at": now_str(), "updated_at": now_str()})
        done, pending, later = work("delivered", "2025-05-08"), work("fabricating", None), work("delivered", "2025-05-20")
        patient = self.q("SELECT id FROM patients LIMIT 1")["id"]
        case = conn.insert("lab_cases", {"lab_id": lab, "branch_id": mal, "patient_id": patient, "case_type": "Crown (PFM)", "status": "delivered",
                                         "sent_on": "2025-05-01", "completed_on": "2025-05-10", "created_at": now_str()})
        for data in ({"work_id": done, "amount": "450"}, {"work_id": pending, "amount": "300"}, {"work_id": later, "amount": "999"},
                     {"case_id": case, "amount": "200", "note": "PFM crown"}):
            r = admin.post("/staff/lab/commission", data={**data, "employee_id": tech})
            self.assertEqual(r.status_code, 302)
        self.assertEqual(conn.scalar("SELECT COUNT(*) FROM lab_commissions WHERE employee_id = ?", (tech,)), 4)
        self.assertIn("Technician commission", admin.get(f"/staff/lab/works/{done}").data.decode())
        # a lab member without the commission permission can't add
        self.assertEqual(self.login("staff.malolos").post("/staff/lab/commission", data={"work_id": done, "employee_id": tech, "amount": "1"}).status_code, 403)
        r = admin.post("/staff/payroll", data={"start_date": "2025-05-01", "end_date": "2025-05-15", "branch_id": mal, "name": "May 1-15"})
        pid = int(r.headers["Location"].rsplit("/", 1)[1])
        line = self.q("SELECT * FROM payroll_lines WHERE period_id = ? AND employee_id = ?", (pid, tech))
        self.assertEqual((line["commission_cents"], line["commission_items"]), (65000, 2))       # 450 + 200; pending and later excluded
        self.assertEqual(line["estimate_cents"], 60000 + 65000)
        detail = admin.get(f"/staff/payroll/{pid}/technician/{tech}").data.decode()
        for part in ("LW-T-delivered-2025-05-08", "Branch case #", "PFM crown", "₱650.00"):
            self.assertIn(part, detail)
