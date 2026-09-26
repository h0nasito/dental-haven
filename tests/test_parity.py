"""MyMedsPH-parity features: permissions, prescriptions, certificates, expenses, account credit, dental chart, lab cases."""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, PW, Base  # noqa: E402


class TestParity(Base):
    def dentist_patient(self, who="dentist.malolos"):
        d = self.q("SELECT id FROM users WHERE email = ?", (who + DOMAIN,))
        p = self.q("SELECT patient_id AS id FROM patient_assignments WHERE dentist_id = ? LIMIT 1", (d["id"],))
        return d["id"], p["id"]

    # --- permissions -------------------------------------------------------
    def test_contact_details_hidden_without_permission(self):
        _, pid = self.dentist_patient()
        phone = self.q("SELECT phone FROM patients WHERE id = ?", (pid,))["phone"]
        r = self.login("dentist.malolos").get(f"/staff/patients/{pid}")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(phone.encode(), r.data)
        self.assertIn(b"Hidden", r.data)
        # grant via Role access, then it shows
        a = self.login("admin")
        current = [f"{x['role']}:{x['permission']}" for x in self.conn.all("SELECT * FROM role_permissions")]
        a.post("/staff/admin/roles", data={"grant": current + ["dentist:patients.contact"]})
        self.assertIn(phone.encode(), self.login("dentist.malolos").get(f"/staff/patients/{pid}").data)
        a.post("/staff/admin/roles", data={"grant": current})

    def test_role_page_uses_mymedsph_groups(self):
        r = self.login("admin").get("/staff/admin/roles")
        for label in (b"View Associates", b"View Birthdays", b"Apply Account Credit", b"Delete patient chart",
                      b"Generate Progress Note", b"Can delete patients", b"View patients with balance", b"Post Expenses"):
            self.assertIn(label, r.data)

    def test_associates_permission(self):
        other = self.q("SELECT a.id FROM appointments a JOIN users u ON u.id = a.dentist_id WHERE u.email = ? LIMIT 1",
                       ("dentist.bocaue" + DOMAIN,))["id"]
        c = self.login("dentist.malolos")
        self.assertEqual(c.get(f"/staff/appointments/{other}").status_code, 403)

    def test_delete_patient(self):
        pid = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? AND active = 1 LIMIT 1", (self.branch("malolos"),))["id"]
        self.assertEqual(self.login("staff.malolos").post(f"/staff/patients/{pid}/delete", data={"reason": "dup"}).status_code, 403)
        a = self.login("admin")
        a.post(f"/staff/patients/{pid}/delete", data={"reason": "Duplicate record"})
        self.assertEqual(self.q("SELECT active FROM patients WHERE id = ?", (pid,))["active"], 0)
        a.post(f"/staff/patients/{pid}/restore")
        self.assertEqual(self.q("SELECT active FROM patients WHERE id = ?", (pid,))["active"], 1)

    # --- prescriptions & certificates ---------------------------------------
    def test_prescription_and_certificate(self):
        did, pid = self.dentist_patient()
        c = self.login("dentist.malolos")
        r = c.post(f"/staff/patients/{pid}/prescriptions/new", data={"prescriber_id": did, "prescribed_on": date.today().isoformat(),
                                                                     "medicine_0": "Mefenamic acid 500 mg", "dosage_0": "500 mg",
                                                                     "quantity_0": "#10", "instructions_0": "1 cap every 8 hours as needed"})
        self.assertEqual(r.status_code, 302)
        rx = self.q("SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY id DESC", (pid,))
        page = c.get(f"/staff/prescriptions/{rx['id']}/print")
        self.assertIn(b"Mefenamic acid", page.data)
        self.assertEqual(self.login("reception.malolos").post(f"/staff/patients/{pid}/prescriptions/new", data={}).status_code, 403)
        self.assertEqual(c.post(f"/staff/prescriptions/{rx['id']}/delete").status_code, 403)  # dentist lacks rx.delete by default
        # certificate: blanks must be filled
        r = c.post(f"/staff/patients/{pid}/certificates/new", data={"kind": "dental", "title": "Dental certificate", "issued_by": did,
                                                                    "issued_on": date.today().isoformat(), "body": "Rest for ____ days"})
        self.assertIn(b"Fill in the blanks", r.data)
        r = c.post(f"/staff/patients/{pid}/certificates/new", data={"kind": "dental", "title": "Dental certificate", "issued_by": did,
                                                                    "issued_on": date.today().isoformat(), "body": "Rest for 2 days."})
        self.assertEqual(r.status_code, 302)
        self.assertIn(b"Rest for 2 days", c.get(r.headers["Location"]).data)

    # --- expenses -----------------------------------------------------------
    def test_expenses_flow(self):
        s = self.login("staff.malolos")
        b = self.branch("malolos")
        today = date.today().isoformat()
        before = self.conn.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM expenses WHERE branch_id = ? AND status = 'posted' "
                                  "AND expense_date = ?", (b, today))
        s.post("/staff/expenses/", data={"branch_id": b, "expense_date": date.today().isoformat(), "category": "Dental supplies",
                                         "amount": "1,234.50", "method": "cash", "description": "Gloves"})
        e = self.q("SELECT * FROM expenses WHERE description = 'Gloves'")
        self.assertEqual((e["status"], e["amount_cents"]), ("draft", 123450))
        self.assertEqual(s.post(f"/staff/expenses/{e['id']}/post").status_code, 403)
        a = self.login("admin")
        a.post(f"/staff/expenses/{e['id']}/post")
        self.assertEqual(self.q("SELECT status FROM expenses WHERE id = ?", (e["id"],))["status"], "posted")
        csv = a.get(f"/staff/reports/export/sales.csv?from={today}&to={today}&branch={b}").data.decode()
        self.assertIn(str((before + 123450) / 100), csv)

    # --- account credit -----------------------------------------------------
    def test_account_credit(self):
        b = self.branch("guiguinto")
        pid = self.q("SELECT id FROM patients WHERE preferred_branch_id = ? AND active = 1 LIMIT 1", (b,))["id"]
        s = self.login("staff.malolos")  # works at Malolos + Guiguinto
        with self.app.app_context():
            from app.billing import credit_balance
            start_credit = credit_balance(self.conn, pid)
        s.post(f"/staff/patients/{pid}/credit", data={"action": "deposit", "amount": "5000", "method": "gcash", "branch_id": b})
        with self.app.app_context():
            self.assertEqual(credit_balance(self.conn, pid) - start_credit, 500000)
        r = s.post("/staff/invoices/new", data={"patient_id": pid, "branch_id": b})
        inv = int(re.search(r"/invoices/(\d+)", r.headers["Location"]).group(1))
        s.post(f"/staff/invoices/{inv}/edit", data={"action": "add_item", "description": "Cleaning", "qty": "1", "unit_price": "3000"})
        s.post(f"/staff/invoices/{inv}/edit", data={"action": "issue"})
        from app import create_app  # noqa
        with self.app.app_context():
            from app.billing import collections
            before = collections(self.conn, [b], date.today().isoformat(), date.today().isoformat())["net"]
        s.post(f"/staff/invoices/{inv}/payments", data={"action": "apply_credit", "amount": "3000"})
        with self.app.app_context():
            after = collections(self.conn, [b], date.today().isoformat(), date.today().isoformat())["net"]
            from app.billing import credit_balance, paid_amount
            self.assertEqual(paid_amount(self.conn, inv), 300000)
            self.assertEqual(credit_balance(self.conn, pid) - start_credit, 200000)
        self.assertEqual(before, after)  # applying credit is not new money
        # receptionist can't apply credit
        self.assertEqual(self.login("reception.guiguinto").post(f"/staff/invoices/{inv}/payments",
                                                               data={"action": "apply_credit", "amount": "1"}).status_code, 403)

    # --- dental chart ------------------------------------------------------
    def test_dental_chart(self):
        _, pid = self.dentist_patient()
        c = self.login("dentist.malolos")
        c.post(f"/staff/patients/{pid}/chart", data={"tooth": "36", "condition": "caries", "surface_O": "1", "note": "deep"})
        e = self.q("SELECT * FROM chart_entries WHERE patient_id = ? AND tooth = '36' AND note = 'deep'", (pid,))
        self.assertEqual((e["condition"], e["surfaces"]), ("caries", "O"))
        page = c.get(f"/staff/patients/{pid}?tab=chart&tooth=36")
        self.assertIn(b"Tooth 36", page.data)
        self.assertEqual(c.post(f"/staff/patients/{pid}/chart", data={"tooth": "99", "condition": "caries"}).status_code, 302)
        self.assertIsNone(self.q("SELECT id FROM chart_entries WHERE tooth = '99'"))
        self.assertEqual(c.post(f"/staff/patients/{pid}/chart/delete", data={"scope": "all"}).status_code, 403)
        self.assertEqual(self.login("reception.malolos").post(f"/staff/patients/{pid}/chart",
                                                              data={"tooth": "11", "condition": "sound"}).status_code, 403)
        self.login("admin").post(f"/staff/patients/{pid}/chart/delete", data={"scope": "all"})
        self.assertIsNone(self.q("SELECT id FROM chart_entries WHERE patient_id = ? AND deleted = 0", (pid,)))

    # --- treatment plan -> progress note --------------------------------------
    def test_generate_progress_note(self):
        did, pid = self.dentist_patient()
        c = self.login("dentist.malolos")
        c.post(f"/staff/patients/{pid}/plans", data={"action": "create", "title": "Plan X"})
        plan = self.q("SELECT id FROM treatment_plans WHERE patient_id = ? AND title = 'Plan X'", (pid,))
        c.post(f"/staff/patients/{pid}/plans", data={"action": "add_item", "plan_id": plan["id"], "description": "Onlay 46", "tooth": "46"})
        item = self.q("SELECT id FROM treatment_plan_items WHERE plan_id = ?", (plan["id"],))
        c.post(f"/staff/patients/{pid}/plans", data={"action": "generate", "plan_id": plan["id"], "item_id": item["id"]})
        self.assertEqual(self.q("SELECT status FROM treatment_plan_items WHERE id = ?", (item["id"],))["status"], "done")
        self.assertIsNotNone(self.q("SELECT id FROM procedures WHERE patient_id = ? AND description = 'Onlay 46'", (pid,)))
        self.assertEqual(c.post(f"/staff/patients/{pid}/plans", data={"action": "delete", "plan_id": plan["id"]}).status_code, 403)

    # --- lab cases ---------------------------------------------------------
    def test_lab_cases_and_lab_only_user(self):
        did, pid = self.dentist_patient()
        c = self.login("dentist.malolos")
        lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        r = c.post("/staff/lab/new", data={"patient_id": pid, "lab_id": lab, "branch_id": self.branch("malolos"), "dentist_id": did,
                                           "case_type": "Crown (zirconia / all-ceramic)", "teeth": "36", "shade": "A2",
                                           "sent_on": date.today().isoformat(), "due_on": "", "lab_fee": "", "material": "", "instructions": "x"})
        self.assertEqual(r.status_code, 302, r.data[:300])
        case_id = int(r.headers["Location"].rstrip("/").split("/")[-1])
        # super admin creates a lab-only user
        a = self.login("admin")
        r = a.post("/staff/admin/users/new", data={"name": "DSDL Tech", "email": "tech@dsdl.test", "role": "staff", "labs": [str(lab)]})
        temp = re.search(rb'id="temp-pw"[^>]*>([^<]+)<', r.data).group(1).decode()
        t = self.app.test_client()
        t.post("/staff/login", data={"email": "tech@dsdl.test", "password": temp})
        t.post("/staff/account/password", data={"current_password": temp, "new_password": "LabTech-2026x", "confirm_password": "LabTech-2026x"})
        self.assertIn(b"Crown (zirconia", t.get("/staff/lab/").data)
        t.post(f"/staff/lab/{case_id}", data={"status": "ready", "note": "Done"})
        self.assertEqual(self.q("SELECT status FROM lab_cases WHERE id = ?", (case_id,))["status"], "ready")
        self.assertIn(t.get(f"/staff/patients/{pid}").status_code, (403, 404))  # lab staff can't open patient records
