import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
from test_app import Base  # noqa: E402


class TestPayslipEmail(Base):
    def _period(self, status="approved"):
        from app.util import now_str
        uid = self.q("SELECT id FROM users WHERE email LIKE 'reception.malolos@%'")["id"]
        e = self.q("SELECT id FROM employees WHERE user_id = ?", (uid,))
        eid = e["id"] if e else self.conn.insert("employees", {"full_name": "Demo Reception", "position": "Staff", "employment_type": "regular",
                                                              "user_id": uid, "primary_branch_id": self.branch("malolos"), "active": 1,
                                                              "created_at": now_str()})
        nolog = self.conn.insert("employees", {"full_name": "Demo No Login", "position": "Staff", "employment_type": "regular",
                                               "primary_branch_id": self.branch("malolos"), "active": 1, "created_at": now_str()})
        pid = self.conn.insert("payroll_periods", {"name": "Demo Nov 1-15", "start_date": "2026-11-01", "end_date": "2026-11-15",
                                                   "status": status, "created_at": now_str()})
        for x in (eid, nolog):
            self.conn.insert("payroll_lines", {"period_id": pid, "employee_id": x})
        return pid, eid, nolog, uid

    def test_send_link_only_and_own_payslip(self):
        pid, eid, nolog, uid = self._period()
        a = self.login("admin")
        self.assertIn("Send payslips by email", a.get(f"/staff/payroll/{pid}").data.decode())
        sent = []
        with mock.patch("app.dentist_mail.config", return_value={"sender": "x"}), \
             mock.patch("app.dentist_mail.send_email", side_effect=lambda to, s, b, c=None: sent.append((to, s, b))), \
             mock.patch.dict(a.application.config, {"APP_ENV": "production"}):
            a.post(f"/staff/payroll/{pid}/payslips/email")
            r = a.post(f"/staff/payroll/{pid}/payslips/email/next")
        self.assertEqual(r.get_json()["left"], 0)
        self.assertEqual(len(sent), 1)
        to, subject, body = sent[0]
        self.assertIn("reception.malolos@", to)
        self.assertIn(f"/staff/my-payslips/{pid}", body)
        self.assertNotIn("₱", body)                                  # no amounts in the email
        self.assertEqual(self.q("SELECT status FROM payslip_emails WHERE employee_id = ?", (nolog,))["status"], "skipped")
        # the employee sees only their own payslip
        c = self.login("reception.malolos")
        self.assertEqual(c.get(f"/staff/my-payslips/{pid}").status_code, 200)
        self.assertIn("Demo Nov 1-15", c.get("/staff/my-payslips").data.decode())
        self.assertNotIn("Demo No Login", c.get(f"/staff/my-payslips/{pid}").data.decode())
        self.assertEqual(c.post(f"/staff/payroll/{pid}/payslips/email").status_code, 403)

    def test_draft_period_cannot_be_sent(self):
        pid, *_ = self._period(status="draft")
        a = self.login("admin")
        a.post(f"/staff/payroll/{pid}/payslips/email")
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM payslip_emails WHERE period_id = ?", (pid,)), 0)
        self.assertEqual(self.login("reception.malolos").get(f"/staff/my-payslips/{pid}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
