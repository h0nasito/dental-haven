"""Reimbursements: file, approve by HR/approver, added once to the salary of the payroll cutoff covering the approval date."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_payroll_rules import TestPayrollRules  # noqa: E402


class TestReimburse(TestPayrollRules):
    for _n in [n for n in dir(TestPayrollRules) if n.startswith("test_")]:
        locals()[_n] = None

    def test_reimbursement_flow_and_payroll(self):
        from app.util import now_str, today
        rec = self.login("reception.malolos")
        emp = self.q("SELECT e.* FROM employees e JOIN users u ON u.id = e.user_id WHERE u.email LIKE 'reception.malolos@%'")
        self.conn.execute("DELETE FROM reimbursements WHERE employee_id = ?", (emp["id"],))
        rec.post("/staff/reimbursements/", data={"category": "Transportation / fare", "amount": "180", "spent_on": today().isoformat(),
                                                 "details": "Tricycle to BDO and back", "reason": "Cash deposit"})
        r = self.q("SELECT * FROM reimbursements WHERE employee_id = ? ORDER BY id DESC LIMIT 1", (emp["id"],))
        self.assertEqual((r["status"], r["amount_cents"]), ("pending", 18000))
        self.assertEqual(rec.post(f"/staff/reimbursements/{r['id']}", data={"action": "approve"}).status_code, 403)
        hr = self.login("admin")
        self.assertIn("Tricycle to BDO", hr.get("/staff/reimbursements/?show=pending").data.decode())
        hr.post(f"/staff/reimbursements/{r['id']}", data={"action": "disapprove"})            # needs a reason
        self.assertEqual(self.q("SELECT status FROM reimbursements WHERE id = ?", (r["id"],))["status"], "pending")
        hr.post(f"/staff/reimbursements/{r['id']}", data={"action": "approve"})
        self.assertEqual(self.q("SELECT status FROM reimbursements WHERE id = ?", (r["id"],))["status"], "approved")
        # approved before this cutoff's end: added to this cutoff's payroll, once
        t = today()
        start, end = (t.replace(day=1), t.replace(day=15)) if t.day <= 15 else (t.replace(day=16), t)
        rr = hr.post("/staff/payroll", data={"start_date": start.isoformat(), "end_date": end.isoformat(), "branch_id": emp["primary_branch_id"],
                                             "name": "Reimb test"})
        pid = int(rr.headers["Location"].rsplit("/", 1)[1])
        item = self.q("SELECT * FROM payroll_items WHERE period_id = ? AND reimbursement_id = ?", (pid, r["id"]))
        self.assertEqual((item["kind"], item["amount_cents"], item["name"]), ("addition", 18000, "Reimbursement"))
        self.assertEqual(self.q("SELECT period_id FROM reimbursements WHERE id = ?", (r["id"],))["period_id"], pid)
        # a second payroll for the same people does not count it again
        rr2 = hr.post("/staff/payroll", data={"start_date": start.isoformat(), "end_date": end.isoformat(), "branch_id": emp["primary_branch_id"],
                                              "name": "Reimb test 2"})
        pid2 = int(rr2.headers["Location"].rsplit("/", 1)[1])
        self.assertIsNone(self.q("SELECT id FROM payroll_items WHERE period_id = ? AND reimbursement_id = ?", (pid2, r["id"])))
        # cancelling the first payroll frees it; recalculating the second one picks it up
        hr.post(f"/staff/payroll/{pid}", data={"action": "cancel"})
        hr.post(f"/staff/payroll/{pid2}", data={"action": "rebuild"})
        self.assertIsNotNone(self.q("SELECT id FROM payroll_items WHERE period_id = ? AND reimbursement_id = ?", (pid2, r["id"])))
        self.assertIn("approved reimbursement", hr.get(f"/staff/payroll/{pid2}").data.decode())
        mine = rec.get("/staff/reimbursements/").data.decode()
        self.assertIn("paid in", mine)
        # an approval after the cutoff's end goes to a later payroll
        self.conn.execute("UPDATE reimbursements SET period_id = NULL, reviewed_at = '2999-01-01 10:00:00' WHERE id = ?", (r["id"],))
        hr.post(f"/staff/payroll/{pid2}", data={"action": "rebuild"})
        self.assertIsNone(self.q("SELECT id FROM payroll_items WHERE period_id = ? AND reimbursement_id = ?", (pid2, r["id"])))
        hr.post(f"/staff/payroll/{pid2}", data={"action": "cancel"})


del TestPayrollRules
