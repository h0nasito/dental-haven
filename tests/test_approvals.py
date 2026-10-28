"""Requests waiting for approval: bell notifications and the morning reminder email."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestApprovals(Base):
    def setUp(self):
        from app.util import now_str
        self.mal = self.branch("malolos")
        self.emp = self.conn.insert("employees", {"full_name": "Approval Test Person (demo)", "position": "Dental assistant",
                                                  "primary_branch_id": self.mal, "active": 1, "ot_eligible": 1, "created_at": now_str()})

    def _admin(self):
        return self.q("SELECT * FROM users WHERE email = 'admin@demo.dentalhaven.test'")

    def test_pending_lists_and_email_text(self):
        from app import approvals
        from app.util import now_str, today
        t = today().isoformat()
        self.conn.insert("leave_requests", {"employee_id": self.emp, "branch_id": self.mal, "leave_type": "Sick leave", "start_date": t,
                                            "end_date": t, "days": 1, "reason": "SECRET-REASON", "status": "pending", "created_at": now_str()})
        self.conn.insert("reimbursements", {"employee_id": self.emp, "branch_id": self.mal, "spent_on": t, "category": "Transport",
                                            "amount_cents": 12345, "status": "pending", "created_at": now_str()})
        self.conn.insert("time_records", {"employee_id": self.emp, "branch_id": self.mal, "work_date": t, "time_in": "08:00",
                                          "time_out": "19:00", "ot_minutes": 120, "created_at": now_str()})
        sections = {s["label"]: s for s in approvals.pending_for(self.conn, self._admin())}
        self.assertIn("Approval Test Person (demo)", sections["Leave forms"]["names"])
        self.assertIn("Reimbursements", sections)
        self.assertIn("Overtime", sections)
        subject, body = approvals.compose(self._admin(), list(sections.values()), "https://clinic.example")
        self.assertIn("waiting for your approval", subject)
        self.assertIn("https://clinic.example/staff/leave/?show=pending", body)
        self.assertNotIn("SECRET-REASON", body)
        self.assertNotIn("123.45", body)
        # a front-desk user with no approval rights sees nothing
        rec = self.q("SELECT * FROM users WHERE email = 'reception.malolos@demo.dentalhaven.test'")
        self.assertEqual([s for s in approvals.pending_for(self.conn, rec) if s["label"] == "Payroll summaries"], [])

    def test_morning_email_once_a_day_and_opt_out(self):
        from app import approvals, settings
        from app.util import now_str, today
        t = today().isoformat()
        self.conn.insert("leave_requests", {"employee_id": self.emp, "branch_id": self.mal, "leave_type": "Vacation leave", "start_date": t,
                                            "end_date": t, "days": 1, "status": "pending", "created_at": now_str()})
        admin = self._admin()
        with self.app.app_context():
            settings.put("approvals.email_time", "00:00", None, self.conn)
            settings.put("approvals.email_last_day", "", None, self.conn)
            self.assertTrue(approvals.run(self.conn))
            self.assertFalse(approvals.run(self.conn))        # once a day
        row = self.q("SELECT * FROM approval_emails WHERE user_id = ? AND sent_day = ?", (admin["id"], t))
        self.assertEqual(row["status"], "demo")                # tests never send
        # opt out
        c = self.login("admin")
        c.post("/staff/account/emails", data={})
        self.assertEqual(self.q("SELECT notify_approvals FROM users WHERE id = ?", (admin["id"],))["notify_approvals"], 0)
        self.conn.execute("DELETE FROM approval_emails")
        with self.app.app_context():
            approvals.send_digests(self.conn, t)
        self.assertIsNone(self.q("SELECT id FROM approval_emails WHERE user_id = ?", (admin["id"],)))
        c.post("/staff/account/emails", data={"notify_approvals": "1"})
        self.assertIn(b"Email me approval reminders", c.get("/staff/account").data)
        # real sending path: email set up → sent through the mail helper
        self.conn.execute("DELETE FROM approval_emails")
        with self.app.app_context():
            self.app.config["TESTING"] = False
            try:
                with mock.patch("app.daily_report._mail_config", return_value={"sender": "x@example.com"}), \
                        mock.patch("app.dentist_mail.send_email") as send:
                    approvals.send_digests(self.conn, t)
            finally:
                self.app.config["TESTING"] = True
        self.assertTrue(send.called)
        self.assertEqual(self.q("SELECT status FROM approval_emails WHERE user_id = ?", (admin["id"],))["status"], "sent")

    def test_bell_for_overtime_and_payroll(self):
        from app.attendance_rules import refresh_record
        from app.util import now_str, today
        admin = self._admin()
        before = self.conn.scalar("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND kind = 'overtime'", (admin["id"],))
        rid = self.conn.insert("time_records", {"employee_id": self.emp, "branch_id": self.mal, "work_date": today().isoformat(),
                                                "time_in": "08:00", "time_out": "19:00", "created_at": now_str()})
        with self.app.app_context():
            refresh_record(self.conn, rid)
        if self.q("SELECT ot_minutes FROM time_records WHERE id = ?", (rid,))["ot_minutes"]:
            self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND kind = 'overtime'", (admin["id"],)), before + 1)
        # payroll submitted → approvers get a bell notification (not the person who submitted)
        hr = self.login("admin")
        pid = self.conn.insert("payroll_periods", {"name": "Approval test cutoff", "start_date": "2026-01-01", "end_date": "2026-01-15",
                                                   "branch_id": self.mal, "status": "draft", "created_at": now_str()})
        hr.post(f"/staff/payroll/{pid}", data={"action": "submit"})
        self.assertEqual(self.q("SELECT status FROM payroll_periods WHERE id = ?", (pid,))["status"], "submitted")
        self.assertIsNone(self.q("SELECT id FROM notifications WHERE user_id = ? AND kind = 'payroll'", (admin["id"],)))

    def test_system_setting_shown(self):
        page = self.login("admin").get("/staff/admin/system").data.decode()
        self.assertIn("Approval reminder emails", page)
