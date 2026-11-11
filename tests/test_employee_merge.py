import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_app import Base  # noqa: E402


class TestEmployeeDuplicates(Base):
    def _emp(self, name, **extra):
        from app.util import now_str
        return self.conn.insert("employees", {"full_name": name, "position": "Staff", "employment_type": "regular",
                                              "primary_branch_id": self.branch("malolos"), "active": 1, "created_at": now_str(), **extra})

    def test_delete_ticked_only_when_empty(self):
        from app.util import now_str
        empty, used = self._emp("Demo Duplicate A"), self._emp("Demo Duplicate B")
        self.conn.insert("time_records", {"employee_id": used, "branch_id": self.branch("malolos"), "work_date": "2026-11-02",
                                          "time_in": "08:00", "created_at": now_str()})
        a = self.login("admin")
        self.assertIn("Delete ticked", a.get("/staff/employees").data.decode())
        a.post("/staff/employees", data={"action": "delete_selected", "emp": [str(empty), str(used)]})
        self.assertIsNone(self.q("SELECT id FROM employees WHERE id = ?", (empty,)))
        self.assertIsNotNone(self.q("SELECT id FROM employees WHERE id = ?", (used,)))
        self.assertEqual(self.login("dentist.malolos").post("/staff/employees", data={"action": "delete_selected", "emp": [str(used)]}).status_code, 403)

    def test_merge_moves_records_and_login(self):
        from app.util import now_str
        uid = self.q("SELECT id FROM users WHERE email LIKE 'staff.bocaue@%'")["id"]
        self.conn.execute("UPDATE employees SET user_id = NULL WHERE user_id = ?", (uid,))
        dup = self._emp("Demo Same Person", user_id=uid)                       # has the login
        keep = self._emp("Demo Same Person")                                   # has the pay rate
        self.conn.insert("time_records", {"employee_id": dup, "branch_id": self.branch("malolos"), "work_date": "2026-11-03",
                                          "time_in": "08:00", "created_at": now_str()})
        a = self.login("admin")
        self.assertIn("Merge into this employee", a.get(f"/staff/employees/{dup}").data.decode())
        a.post(f"/staff/employees/{dup}/merge", data={"into": str(keep)})
        self.assertIsNone(self.q("SELECT id FROM employees WHERE id = ?", (dup,)))
        self.assertEqual(self.q("SELECT user_id FROM employees WHERE id = ?", (keep,))["user_id"], uid)
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM time_records WHERE employee_id = ?", (keep,)), 1)

    def test_merge_refused_when_both_have_the_same_day(self):
        from app.util import now_str
        a1, a2 = self._emp("Demo Clash"), self._emp("Demo Clash")
        for e in (a1, a2):
            self.conn.insert("time_records", {"employee_id": e, "branch_id": self.branch("malolos"), "work_date": "2026-11-04",
                                              "time_in": "08:00", "created_at": now_str()})
        self.login("admin").post(f"/staff/employees/{a1}/merge", data={"into": str(a2)})
        self.assertIsNotNone(self.q("SELECT id FROM employees WHERE id = ?", (a1,)))


if __name__ == "__main__":
    unittest.main()


class TestMergeDraftPayroll(Base):
    _emp = TestEmployeeDuplicates._emp

    def test_draft_payroll_line_of_the_duplicate_is_dropped(self):
        from app.util import now_str
        a1, a2 = self._emp("Demo Payroll Twin"), self._emp("Demo Payroll Twin")
        per = self.conn.insert("payroll_periods", {"name": "Demo period", "start_date": "2026-11-01", "end_date": "2026-11-15", "status": "draft",
                                                   "created_at": now_str()})
        for e in (a1, a2):
            self.conn.insert("payroll_lines", {"period_id": per, "employee_id": e})
        r = self.login("admin").post(f"/staff/employees/{a1}/merge", data={"into": str(a2)}, follow_redirects=True)
        self.assertIn("Recalculate from DTR", r.data.decode())
        self.assertIsNone(self.q("SELECT id FROM employees WHERE id = ?", (a1,)))
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM payroll_lines WHERE period_id = ?", (per,)), 1)

    def test_approved_payroll_still_blocks(self):
        from app.util import now_str
        a1, a2 = self._emp("Demo Approved Twin"), self._emp("Demo Approved Twin")
        per = self.conn.insert("payroll_periods", {"name": "Demo period", "start_date": "2026-10-16", "end_date": "2026-10-31", "status": "approved",
                                                   "created_at": now_str()})
        for e in (a1, a2):
            self.conn.insert("payroll_lines", {"period_id": per, "employee_id": e})
        self.login("admin").post(f"/staff/employees/{a1}/merge", data={"into": str(a2)})
        self.assertIsNotNone(self.q("SELECT id FROM employees WHERE id = ?", (a1,)))
