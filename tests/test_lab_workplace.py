"""Employees can work at the laboratory (DSDL); the lab has its own payroll."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_payroll_rules import TestPayrollRules  # noqa: E402


class TestLabWorkplace(TestPayrollRules):
    for _n in [n for n in dir(TestPayrollRules) if n.startswith("test_")]:
        locals()[_n] = None

    def test_dsdl_employee_and_payroll(self):
        admin = self.login("admin")
        lab = self.q("SELECT id FROM laboratories WHERE name = 'DSDL'")["id"]
        page = admin.get("/staff/employees").data.decode()
        self.assertIn(f'value="lab:{lab}"', page)
        admin.post("/staff/employees", data={"full_name": "Lab Tech QW", "position": "Technician", "primary_branch_id": f"lab:{lab}",
                                             "employment_type": "regular"})
        e = self.q("SELECT * FROM employees WHERE full_name = 'Lab Tech QW'")
        self.assertEqual((e["lab_id"], e["primary_branch_id"]), (lab, None))
        self.assertIn("DSDL (laboratory)", admin.get("/staff/employees").data.decode())
        # its own payroll: the lab employee is in the DSDL period, not in a branch period
        self.assertIn(f'value="lab:{lab}"', admin.get("/staff/payroll").data.decode())
        r = admin.post("/staff/payroll", data={"start_date": "2026-09-01", "end_date": "2026-09-15", "branch_id": f"lab:{lab}", "name": "DSDL QW"})
        pid = int(r.headers["Location"].rsplit("/", 1)[1])
        self.assertEqual(self.q("SELECT lab_id FROM payroll_periods WHERE id = ?", (pid,))["lab_id"], lab)
        emp_ids = {x["employee_id"] for x in self.conn.all("SELECT employee_id FROM payroll_lines WHERE period_id = ?", (pid,))}
        self.assertIn(e["id"], emp_ids)
        branch_emps = {x["id"] for x in self.conn.all("SELECT id FROM employees WHERE lab_id IS NULL AND active = 1")}
        self.assertFalse(emp_ids & branch_emps)
        self.assertIn("DSDL (laboratory)", admin.get(f"/staff/payroll/{pid}").data.decode())
        r2 = admin.post("/staff/payroll", data={"start_date": "2026-09-01", "end_date": "2026-09-15", "branch_id": str(self.branch("malolos")), "name": "MAL QW"})
        pid2 = int(r2.headers["Location"].rsplit("/", 1)[1])
        self.assertNotIn(e["id"], {x["employee_id"] for x in self.conn.all("SELECT employee_id FROM payroll_lines WHERE period_id = ?", (pid2,))})
        # move back to a branch from the employee page
        admin.post(f"/staff/employees/{e['id']}", data={"action": "details", "position": "Technician", "primary_branch_id": str(self.branch("malolos")),
                                                       "employment_type": "regular", "active": "1"})
        e2 = self.q("SELECT * FROM employees WHERE id = ?", (e["id"],))
        self.assertEqual((e2["lab_id"], e2["primary_branch_id"]), (None, self.branch("malolos")))
        # a branch receptionist can't add to the lab
        self.assertNotIn(f'value="lab:{lab}"', self.login("reception.malolos").get("/staff/employees").data.decode() or "")
        for p in (pid, pid2):
            admin.post(f"/staff/payroll/{p}", data={"action": "cancel"})


del TestPayrollRules
