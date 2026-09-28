"""Clinic pay rules: cutoffs, ₱1/min late, supervisor-approved overtime, holiday pay, 3-lates warning, staff access roles."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import PW, Base  # noqa: E402


class TestPayrollRules(Base):
    def _employee(self, name="Rules Test Assistant"):
        from app.util import now_str
        bid = self.branch("malolos")
        eid = self.conn.insert("employees", {"full_name": name, "position": "Dental assistant", "employment_type": "regular",
                                             "primary_branch_id": bid, "active": 1, "created_at": now_str()})
        self.conn.insert("compensation", {"employee_id": eid, "basis": "daily", "rate_cents": 70000, "effective_from": "2020-01-01",
                                          "created_at": now_str()})
        return eid, bid

    def _record(self, c, eid, bid, day, tin, tout):
        from app.util import now_str
        r = c.post("/staff/attendance/record", data={"employee_id": eid, "branch_id": bid, "work_date": day, "time_in": tin, "time_out": tout})
        self.assertEqual(r.status_code, 302)
        return self.q("SELECT * FROM time_records WHERE employee_id = ? AND work_date = ?", (eid, day))

    def test_staff_pay_holidays_overtime_and_lates(self):
        from app import settings
        settings.put("payroll.grace_minutes", 0, None, self.conn)
        admin = self.login("admin")
        eid, bid = self._employee()
        hours = self.q("SELECT open_time, close_time FROM branch_hours WHERE branch_id = ? AND weekday = 1", (bid,))
        self.assertEqual((hours["open_time"], hours["close_time"]), ("09:00", "18:00"))
        # holidays: 2025-04-02 special (worked), 2025-04-09 regular (worked), 2025-04-10 regular (not worked)
        admin.post("/staff/holidays", data={"action": "add", "day": "2025-04-02", "name": "Test special", "kind": "special"})
        admin.post("/staff/holidays", data={"action": "add", "day": "2025-04-09", "name": "Araw ng Kagitingan", "kind": "regular"})
        admin.post("/staff/holidays", data={"action": "add", "day": "2025-04-10", "name": "Test regular", "kind": "regular"})
        r1 = self._record(admin, eid, bid, "2025-04-01", "09:05", "19:00")   # 5 min late, 60 min after closing
        self.assertEqual((r1["late_minutes"], r1["ot_minutes"], r1["ot_approved_minutes"]), (5, 60, 0))
        self._record(admin, eid, bid, "2025-04-02", "09:00", "18:00")
        self._record(admin, eid, bid, "2025-04-09", "09:00", "18:00")
        # overtime counts only once approved
        r = admin.post(f"/staff/attendance/{r1['id']}/overtime", data={"minutes": "90", "note": "x"})
        self.assertEqual(self.q("SELECT ot_approved_minutes FROM time_records WHERE id = ?", (r1["id"],))["ot_approved_minutes"], 0)  # > detected
        admin.post(f"/staff/attendance/{r1['id']}/overtime", data={"minutes": "60", "note": "Late patient"})
        self.assertEqual(self.q("SELECT ot_approved_minutes FROM time_records WHERE id = ?", (r1["id"],))["ot_approved_minutes"], 60)
        self.assertEqual(self.login("reception.malolos").post(f"/staff/attendance/{r1['id']}/overtime", data={"minutes": "0"}).status_code, 403)
        # cutoff defaults on the payroll page
        page = admin.get("/staff/payroll").data.decode()
        self.assertIn("Cutoffs are the 1st–15th and the 16th–end", page)
        r = admin.post("/staff/payroll", data={"start_date": "2025-04-01", "end_date": "2025-04-15", "branch_id": bid, "name": "Apr 1-15"})
        pid = int(r.headers["Location"].rsplit("/", 1)[1])
        line = self.q("SELECT * FROM payroll_lines WHERE period_id = ? AND employee_id = ?", (pid, eid))
        # basic 3 x 700; holiday: special +210, regular worked +700, regular unworked +700; OT 1h x 700/8 x 1.25 = 109.38; late 5 x ₱1
        self.assertEqual((line["basic_pay_cents"], line["holiday_pay_cents"], line["ot_minutes"], line["ot_pay_cents"], line["late_deduction_cents"]),
                         (210000, 161000, 60, 10938, 500))
        self.assertEqual(line["estimate_cents"], 210000 + 161000 + 10938 - 500)
        html = admin.get(f"/staff/payroll/{pid}").data.decode()
        for part in ("₱1,610.00", "₱109.38", "-₱5.00", "Night differential and statutory deductions"):
            self.assertIn(part, html)

    def test_third_late_in_a_month_warns(self):
        admin = self.login("admin")
        eid, bid = self._employee("Often Late (demo)")
        for day in ("2025-06-02", "2025-06-03"):
            self._record(admin, eid, bid, day, "09:10", "18:00")
        self.assertIsNone(self.q("SELECT id FROM late_warnings WHERE employee_id = ?", (eid,)))
        self._record(admin, eid, bid, "2025-06-04", "09:02", "18:00")
        w = self.q("SELECT * FROM late_warnings WHERE employee_id = ?", (eid,))
        self.assertEqual((w["month"], w["late_count"]), ("2025-06", 3))
        admin_id = self.q("SELECT id FROM users WHERE email = 'admin@demo.dentalhaven.test'")["id"]
        self.assertTrue(self.q("SELECT id FROM notifications WHERE user_id = ? AND title LIKE 'Late warning: Often Late%'", (admin_id,)))
        self._record(admin, eid, bid, "2025-06-05", "09:30", "18:00")   # 4th late: no second warning
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM late_warnings WHERE employee_id = ?", (eid,)), 1)
        self.assertIn("Late warnings", admin.get("/staff/attendance").data.decode())

    def test_staff_access_roles(self):
        admin = self.login("admin")
        bid = self.branch("bocaue")
        for role, email in (("hr", "hr.test@demo.dentalhaven.test"), ("cashier", "cashier.test@demo.dentalhaven.test"),
                            ("supervisor", "sup.test@demo.dentalhaven.test")):
            r = admin.post("/staff/admin/users/new", data={"name": f"{role} tester", "email": email, "role": role, "branches": str(bid),
                                                         "is_employee": "1"})
            self.assertEqual(r.status_code, 200)
            u = self.q("SELECT * FROM users WHERE email = ?", (email,))
            self.assertEqual((u["role"], u["access_role"]), ("staff", role))
            self.conn.execute("UPDATE users SET must_change_password = 0, password_hash = (SELECT password_hash FROM users WHERE email = "
                              "'admin@demo.dentalhaven.test') WHERE id = ?", (u["id"],))
        def client(email):
            c = self.app.test_client()
            c.post("/staff/login", data={"email": email, "password": PW})
            return c
        hr, cashier, sup = (client(e) for e in ("hr.test@demo.dentalhaven.test", "cashier.test@demo.dentalhaven.test", "sup.test@demo.dentalhaven.test"))
        self.assertEqual(hr.get("/staff/payroll").status_code, 200)
        self.assertEqual(cashier.get("/staff/payroll").status_code, 403)
        self.assertEqual(cashier.get("/staff/invoices").status_code, 200)
        self.assertIn("Staff – Cashier", cashier.get("/staff/invoices").data.decode())
        self.assertIn("Overtime to approve", sup.get("/staff/attendance").data.decode())
        roles_page = admin.get("/staff/admin/roles").data.decode()
        for label in ("Staff – HR", "Staff – Supervisor", "Staff – Cashier", "Staff – Receptionist"):
            self.assertIn(label, roles_page)

    def test_positions_and_only_super_admin_assigns_roles(self):
        admin = self.login("admin")
        r = admin.post("/staff/admin/users/new", data={"name": "Tech Tester", "email": "tech.tester@demo.dentalhaven.test", "role": "technician",
                                                     "branches": str(self.branch("malolos")), "is_employee": "1"})
        self.assertEqual(r.status_code, 200)
        u = self.q("SELECT * FROM users WHERE email = 'tech.tester@demo.dentalhaven.test'")
        self.assertEqual((u["role"], u["access_role"]), ("staff", "technician"))
        emp = self.q("SELECT * FROM employees WHERE user_id = ?", (u["id"],))
        self.assertEqual(emp["position"], "Technician")
        form = admin.get("/staff/admin/users/new").data.decode()
        for pos in ("Receptionist", "Cashier", "Technician", "Staff", "Dentist", "HR", "Supervisor"):
            self.assertIn(f"<option >{pos}</option>", form.replace("<option>", "<option >"))
        # HR (attendance.manage) can change the position but can't open users or role access
        self.conn.execute("UPDATE users SET access_role = 'hr', must_change_password = 0, password_hash = (SELECT password_hash FROM users "
                          "WHERE email = 'admin@demo.dentalhaven.test') WHERE id = ?", (u["id"],))
        hr = self.app.test_client()
        hr.post("/staff/login", data={"email": "tech.tester@demo.dentalhaven.test", "password": PW})
        self.assertEqual(hr.get("/staff/admin/users/new").status_code, 403)
        self.assertEqual(hr.get("/staff/admin/roles").status_code, 403)
        self.assertEqual(hr.post(f"/staff/admin/users/{u['id']}", data={"role": "super_admin"}).status_code, 403)
        hr.post(f"/staff/employees/{emp['id']}", data={"action": "details", "position": "Supervisor", "employment_type": "regular",
                                                       "primary_branch_id": self.branch("malolos"), "active": "1"})
        self.assertEqual(self.q("SELECT position FROM employees WHERE id = ?", (emp["id"],))["position"], "Supervisor")
        self.assertEqual(self.q("SELECT access_role FROM users WHERE id = ?", (u["id"],))["access_role"], "hr")  # position doesn't change access
        hr.post(f"/staff/employees/{emp['id']}", data={"action": "details", "position": "Chief", "employment_type": "regular",
                                                       "primary_branch_id": self.branch("malolos"), "active": "1"})
        self.assertEqual(self.q("SELECT position FROM employees WHERE id = ?", (emp["id"],))["position"], "Supervisor")  # not in the list
