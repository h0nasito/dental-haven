"""My cases: dentists see their assigned patients' cases by type (view only), with payments and ortho monthly adjustments."""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestCases(Base):
    def test_ortho_case_with_payments_and_adjustments(self):
        from app.util import now_str, today
        doc = self.q("SELECT id FROM users WHERE email LIKE 'dentist.malolos@%'")["id"]
        bid = self.branch("malolos")
        pid = self.conn.insert("patients", {"first_name": "Orthocase", "last_name": "Testpatient", "chart_no": "DH-TCASE1", "preferred_branch_id": bid,
                                            "created_at": now_str(), "updated_at": now_str()})
        self.conn.execute("INSERT INTO patient_assignments (patient_id, dentist_id, created_at) VALUES (?, ?, ?)", (pid, doc, now_str()))
        svc = self.q("SELECT id FROM services WHERE category = 'Orthodontics & TMJ' LIMIT 1")["id"]
        t = today()
        # visits 4 and 2 months ago, none in between or since: overdue
        for back in (120, 60):
            d = (t - timedelta(days=back)).isoformat()
            self.conn.insert("procedures", {"patient_id": pid, "service_id": svc, "branch_id": bid, "description": "Braces adjustment", "status": "completed",
                                            "performed_by": doc, "performed_at": d + " 10:00:00", "created_at": d + " 10:00:00"})
        inv = self.conn.insert("invoices", {"branch_id": bid, "patient_id": pid, "status": "issued", "issued_at": now_str(), "number": "TCASE-1",
                                            "subtotal_cents": 4500000, "total_cents": 4500000, "created_at": now_str()})
        self.conn.insert("invoice_items", {"invoice_id": inv, "service_id": svc, "description": "Braces", "qty": 1, "unit_price_cents": 4500000,
                                           "amount_cents": 4500000, "dentist_id": doc})
        self.conn.insert("payments", {"invoice_id": inv, "branch_id": bid, "kind": "payment", "amount_cents": 1000000, "method": "cash",
                                      "received_at": now_str(), "status": "valid", "created_at": now_str()})
        d = self.login("dentist.malolos")
        page = d.get("/staff/my-cases/?type=Braces%2C+Aligners+%26+Orthodontics&q=orthocase").data.decode()
        self.assertIn("Testpatient, Orthocase", page)
        self.assertIn("Adjustment overdue", page)
        self.assertIn("₱35,000.00", page)                       # balance
        # date filter: a visit 60 days ago is inside the last 90 days, not inside the last 30
        f90, f30 = (t - timedelta(days=90)).isoformat(), (t - timedelta(days=30)).isoformat()
        self.assertIn("Orthocase", d.get(f"/staff/my-cases/?q=orthocase&from={f90}&to={t.isoformat()}").data.decode())
        self.assertNotIn("Testpatient, Orthocase", d.get(f"/staff/my-cases/?q=orthocase&from={f30}&to={t.isoformat()}").data.decode())
        self.assertIn("Procedure", page)
        detail = d.get(f"/staff/my-cases/{pid}?type=Braces%2C+Aligners+%26+Orthodontics").data.decode()
        self.assertIn("Monthly adjustments", detail)
        self.assertIn("TCASE-1", detail)
        self.assertIn("₱10,000.00", detail)
        self.assertNotIn("<form method=\"post\"", detail.split('<main')[1])  # view only
        # another dentist doesn't see it; receptionists can't open My cases
        other = self.login("dentist.sjdm")
        self.assertNotIn("Orthocase", other.get("/staff/my-cases/").data.decode())
        self.assertEqual(other.get(f"/staff/my-cases/{pid}?type=Braces%2C+Aligners+%26+Orthodontics").status_code, 404)
        self.assertEqual(self.login("reception.malolos").get("/staff/my-cases/").status_code, 403)
        # super admin can choose the dentist
        self.assertIn("Orthocase", self.login("admin").get(f"/staff/my-cases/?dentist={doc}").data.decode())

    def test_only_assigned_and_billed(self):
        """A patient assigned to the dentist shows only for the types of case billed to that dentist."""
        from app.util import now_str, today
        doc = self.q("SELECT id FROM users WHERE email LIKE 'dentist.malolos@%'")["id"]
        other = self.q("SELECT id FROM users WHERE email LIKE 'dentist.sjdm@%'")["id"]
        bid = self.branch("malolos")
        pid = self.conn.insert("patients", {"first_name": "Billedqt", "last_name": "Assignedqt", "chart_no": "DH-QABQ", "preferred_branch_id": bid,
                                            "created_at": now_str(), "updated_at": now_str()})
        nobill = self.conn.insert("patients", {"first_name": "Nobillqt", "last_name": "Assignedqt", "chart_no": "DH-QANB", "preferred_branch_id": bid,
                                               "created_at": now_str(), "updated_at": now_str()})
        for p_ in (pid, nobill):
            self.conn.execute("INSERT INTO patient_assignments (patient_id, dentist_id, created_at) VALUES (?, ?, ?)", (p_, doc, now_str()))
        d = today().isoformat()
        self.conn.insert("visit_notes", {"patient_id": nobill, "branch_id": bid, "dentist_id": doc, "visit_date": d, "status": "saved",
                                         "body": "Check-up", "created_at": now_str()})
        ortho = self.q("SELECT id FROM services WHERE category = 'Orthodontics & TMJ' LIMIT 1")["id"]
        inv = self.conn.insert("invoices", {"branch_id": bid, "patient_id": pid, "status": "issued", "issued_at": now_str(), "number": "TQAB-1",
                                            "subtotal_cents": 300000, "total_cents": 300000, "created_at": now_str()})
        self.conn.insert("invoice_items", {"invoice_id": inv, "service_id": ortho, "description": "Braces", "qty": 1, "unit_price_cents": 200000,
                                           "amount_cents": 200000, "dentist_id": doc})
        self.conn.insert("invoice_items", {"invoice_id": inv, "description": "ORAL PROPHYLAXIS (MILD)", "qty": 1, "unit_price_cents": 100000,
                                           "amount_cents": 100000, "dentist_id": other})
        from app.views.cases import build_cases
        with self.app.app_context():
            from app.db import get_db as gdb
            mine = [(c["patient_id"], c["category"], c["billed"]) for c in build_cases(gdb(), doc) if c["patient_id"] in (pid, nobill)]
        self.assertEqual(mine, [(pid, "Braces, Aligners & Orthodontics", 200000)])   # not the other dentist's cleaning, not the unbilled patient

    def test_visits_count_days_and_name_matched_type(self):
        """Several procedures on one day = one visit; a procedure without a service but named like one gets its type."""
        from app.util import now_str, today
        doc = self.q("SELECT id FROM users WHERE email LIKE 'dentist.malolos@%'")["id"]
        bid = self.branch("malolos")
        pid = self.conn.insert("patients", {"first_name": "Dayvisit", "last_name": "Countqt", "chart_no": "DH-QDAY1", "preferred_branch_id": bid,
                                            "created_at": now_str(), "updated_at": now_str()})
        self.conn.execute("INSERT INTO patient_assignments (patient_id, dentist_id, created_at) VALUES (?, ?, ?)", (pid, doc, now_str()))
        svc = self.q("SELECT id, name FROM services WHERE category = 'Orthodontics & TMJ' LIMIT 1")
        d = today().isoformat()
        for i, (sid, desc) in enumerate(((svc["id"], "Braces"), (None, svc["name"].upper()), (svc["id"], "Adjustment"))):
            self.conn.insert("procedures", {"patient_id": pid, "service_id": sid, "branch_id": bid, "description": desc, "status": "completed",
                                            "performed_by": doc, "performed_at": f"{d} 1{i}:00:00", "created_at": now_str()})
        inv = self.conn.insert("invoices", {"branch_id": bid, "patient_id": pid, "status": "issued", "issued_at": now_str(), "number": "TQDAY-1",
                                            "subtotal_cents": 100000, "total_cents": 100000, "created_at": now_str()})
        self.conn.insert("invoice_items", {"invoice_id": inv, "service_id": svc["id"], "description": "Braces", "qty": 1, "unit_price_cents": 100000,
                                           "amount_cents": 100000, "dentist_id": doc})
        from app.db import get_db  # noqa: F401
        from app.views.cases import build_cases
        with self.app.app_context():
            from app.db import get_db as gdb
            cases = [c for c in build_cases(gdb(), doc) if c["patient_id"] == pid]
        self.assertEqual([(c["category"], c["n"]) for c in cases], [("Braces, Aligners & Orthodontics", 1)])
        page = self.login("dentist.malolos").get(f"/staff/my-cases/{pid}?type=Braces%2C Aligners %26 Orthodontics").data.decode()
        self.assertIn("3 procedures", page)
        self.assertNotIn("None", page)
