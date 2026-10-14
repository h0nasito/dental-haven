"""Announcements and the monthly duty schedule: managers post and set duties; everyone sees them; staff can't edit."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_payroll_rules import TestPayrollRules  # noqa: E402


class TestAnnouncements(TestPayrollRules):
    for _n in [n for n in dir(TestPayrollRules) if n.startswith("test_")]:
        locals()[_n] = None

    def test_announcements_and_duty(self):
        from app.util import today
        t = today()
        month = t.strftime("%Y-%m")
        rec = self.login("reception.malolos")
        emp = self.q("SELECT e.* FROM employees e JOIN users u ON u.id = e.user_id WHERE u.email LIKE 'reception.malolos@%'")
        bid = emp["primary_branch_id"]
        # staff can read but not post or edit
        self.assertEqual(rec.get("/staff/announcements/").status_code, 200)
        self.assertEqual(rec.post("/staff/announcements/post", data={"title": "x"}).status_code, 403)
        self.assertEqual(rec.get(f"/staff/announcements/duty/edit?branch={bid}&month={month}").status_code, 403)
        admin = self.login("admin")
        admin.post("/staff/announcements/post", data={"title": "Holiday closing Friday", "body": "Clinic closed.", "branch_id": "",
                                                      "starts_on": t.isoformat(), "notify": "1", "pinned": "1"})
        a = self.q("SELECT * FROM announcements WHERE title = 'Holiday closing Friday'")
        self.assertEqual(a["pinned"], 1)
        self.assertIsNotNone(self.q("SELECT id FROM notifications WHERE user_id = ? AND kind = 'announcement'", (emp["user_id"],)))
        self.assertIn("Holiday closing Friday", rec.get("/staff/announcements/").data.decode())
        self.assertIn("Holiday closing Friday", rec.get("/staff/").data.decode())
        # an announcement for another branch only is not shown to this receptionist
        other = self.q("SELECT id FROM branches WHERE id != ? AND active = 1", (bid,))
        if other and not self.q("SELECT 1 AS x FROM user_branches WHERE user_id = ? AND branch_id = ?", (emp["user_id"], other["id"])):
            admin.post("/staff/announcements/post", data={"title": "Other branch only", "branch_id": other["id"], "starts_on": t.isoformat()})
            self.assertNotIn("Other branch only", rec.get("/staff/announcements/").data.decode())
        # duty: the editing grid lists the branch's employees; a weekday pattern fills the whole month
        page = admin.get(f"/staff/announcements/duty/edit?branch={bid}&month={month}").data.decode()
        self.assertIn(emp["full_name"], page)
        admin.post("/staff/announcements/duty/edit", data={"branch": bid, "month": month, f"w_{emp['id']}": str(t.weekday()),
                                                           "notify": "1"})
        rows = self.conn.all("SELECT work_date FROM duty_assignments WHERE employee_id = ? AND branch_id = ?", (emp["id"], bid))
        self.assertIn(t.isoformat(), [r["work_date"] for r in rows])
        self.assertTrue(all(__import__("datetime").date.fromisoformat(r["work_date"]).weekday() == t.weekday() for r in rows))
        self.assertIsNotNone(self.q("SELECT id FROM notifications WHERE user_id = ? AND kind = 'duty'", (emp["user_id"],)))
        self.assertIn(emp["full_name"], rec.get("/staff/").data.decode())
        self.assertIn(emp["full_name"], rec.get(f"/staff/announcements/duty?branch={bid}&month={month}").data.decode())
        # saving again with only one ticked day replaces the month
        admin.post("/staff/announcements/duty/edit", data={"branch": bid, "month": month, f"d_{emp['id']}": t.isoformat()})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM duty_assignments WHERE employee_id = ? AND branch_id = ?", (emp["id"], bid))["n"], 1)
        admin.post(f"/staff/announcements/{a['id']}/delete")
        self.assertIsNone(self.q("SELECT id FROM announcements WHERE id = ?", (a["id"],)))


del TestPayrollRules
