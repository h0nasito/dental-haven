"""An associate dentist's own hours (Dentist schedule setup) are used for lateness, not the branch opening time."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402

from app.attendance_rules import day_metrics, schedule  # noqa: E402


class TestAssociateHours(Base):
    def test_own_schedule_counts(self):
        from app.util import now_str
        uid = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        emp = self.q("SELECT id FROM employees WHERE user_id = ?", (uid,))
        emp_id = emp["id"] if emp else self.conn.insert("employees", {"user_id": uid, "full_name": "Assoc", "created_at": now_str()})
        b = self.branch("malolos")
        day = "2026-10-21"       # a Wednesday
        rec = {"work_date": day, "branch_id": b, "employee_id": emp_id, "time_in": "10:20", "time_out": "18:00"}
        self.conn.execute("DELETE FROM dentist_schedules WHERE dentist_id = ? AND branch_id = ? AND weekday = 2", (uid, b))
        opening = schedule(self.conn, rec)["start"]
        self.conn.execute("INSERT INTO dentist_schedules (dentist_id, branch_id, weekday, start_time, end_time) VALUES (?, ?, 2, '10:00', '18:00')", (uid, b))
        sch = schedule(self.conn, rec)
        self.assertEqual((sch["start"], sch["end"], sch["dentist"]), ("10:00", "18:00", True))
        self.assertEqual(day_metrics(self.conn, rec)[0], 20)
        self.assertEqual(day_metrics(self.conn, dict(rec, time_in="09:58"))[0], 0)
        self.assertNotEqual(opening, "10:00")

    def test_employee_work_hours_win_and_form_saves(self):
        from app.util import now_str
        uid = self.q("SELECT id FROM users WHERE email = ?", ("staff.malolos" + DOMAIN,))["id"]
        emp = self.q("SELECT id FROM employees WHERE user_id = ?", (uid,))
        emp_id = emp["id"] if emp else self.conn.insert("employees", {"user_id": uid, "full_name": "Staff", "created_at": now_str()})
        a = self.login("admin")
        page = a.get(f"/staff/employees/{emp_id}").data.decode()
        self.assertIn("Work hours", page)
        cur = self.q("SELECT position, employment_type FROM employees WHERE id = ?", (emp_id,))
        form = {"primary_branch_id": str(self.branch("malolos")), "position": cur["position"], "employment_type": cur["employment_type"] or "regular"}
        r = a.post(f"/staff/employees/{emp_id}", data={"action": "details", **form, "active": "1", "work_start": "10:00", "work_end": "18:00"})
        self.assertEqual(r.status_code, 302)
        e = self.q("SELECT work_start, work_end FROM employees WHERE id = ?", (emp_id,))
        self.assertEqual((e["work_start"], e["work_end"]), ("10:00", "18:00"))
        rec = {"work_date": "2026-10-21", "branch_id": self.branch("malolos"), "employee_id": emp_id, "time_in": "10:05", "time_out": "18:00"}
        self.assertEqual(day_metrics(self.conn, rec)[0], 5)
        a.post(f"/staff/employees/{emp_id}", data={"action": "details", **form, "active": "1", "work_start": "10:00", "work_end": ""})
        self.assertEqual(self.q("SELECT work_end FROM employees WHERE id = ?", (emp_id,))["work_end"], "18:00")   # half-filled: refused
