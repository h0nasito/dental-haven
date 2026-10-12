"""Leave forms: file, approve / disapprove by someone with leave.approve, DTR marked excused, no self-approval, cancel."""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestLeave(Base):
    def _emp(self, who):
        return self.q("SELECT e.* FROM employees e JOIN users u ON u.id = e.user_id WHERE u.email LIKE ?", (who + "@%",))

    def test_file_approve_disapprove_cancel(self):
        from app.util import today
        rec = self.login("reception.malolos")
        emp = self._emp("reception.malolos")
        self.conn.execute("DELETE FROM time_records WHERE employee_id = ?", (emp["id"],))
        self.conn.execute("DELETE FROM leave_requests WHERE employee_id = ?", (emp["id"],))
        d1 = today() + timedelta(days=7)
        while d1.weekday() != 0:
            d1 += timedelta(days=1)          # a Monday
        d3 = d1 + timedelta(days=6)          # next Sunday: not counted
        rec.post("/staff/leave/", data={"reliever": "na", "leave_type": "Vacation leave", "start_date": d1.isoformat(), "end_date": d3.isoformat(), "reason": "Family trip"})
        lr = self.q("SELECT * FROM leave_requests WHERE employee_id = ? ORDER BY id DESC LIMIT 1", (emp["id"],))
        self.assertEqual((lr["status"], lr["days"]), ("pending", 6.0))
        # overlapping leave refused
        rec.post("/staff/leave/", data={"reliever": "na", "leave_type": "Sick leave", "start_date": d1.isoformat(), "end_date": d1.isoformat(), "reason": "x y z"})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM leave_requests WHERE employee_id = ?", (emp["id"],))["n"], 1)
        # a receptionist can't approve
        self.assertEqual(rec.post(f"/staff/leave/{lr['id']}", data={"action": "approve"}).status_code, 403)
        # admin (approver) is notified and sees it, then approves
        admin_id = self.q("SELECT id FROM users WHERE email LIKE 'admin@%'")["id"]
        self.assertTrue(self.q("SELECT id FROM notifications WHERE user_id = ? AND kind = 'leave'", (admin_id,)))
        a = self.login("admin")
        self.assertIn("Family trip", a.get("/staff/leave/?show=pending").data.decode())
        a.post(f"/staff/leave/{lr['id']}", data={"action": "approve", "note": "Enjoy"})
        self.assertEqual(self.q("SELECT status FROM leave_requests WHERE id = ?", (lr["id"],))["status"], "approved")
        days = self.conn.all("SELECT status, exception_note FROM time_records WHERE employee_id = ? AND work_date BETWEEN ? AND ?",
                             (emp["id"], d1.isoformat(), d3.isoformat()))
        self.assertEqual(len(days), 6)
        self.assertTrue(all(r["status"] == "excused" and r["exception_note"].startswith("On leave") for r in days))
        self.assertIn("Your leave was approved", " ".join(r["title"] for r in self.conn.all(
            "SELECT title FROM notifications WHERE user_id = ?", (emp["user_id"],))))
        # the employee cancels the approved future leave: the DTR days are removed again
        rec.post(f"/staff/leave/{lr['id']}", data={"action": "cancel"})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM time_records WHERE employee_id = ? AND source = 'leave'", (emp["id"],))["n"], 0)
        # disapprove needs a reason
        rec.post("/staff/leave/", data={"reliever": "na", "leave_type": "Sick leave", "start_date": d1.isoformat(), "end_date": d1.isoformat(),
                                        "half_day": "am", "reason": "Check-up"})
        lr2 = self.q("SELECT * FROM leave_requests WHERE employee_id = ? ORDER BY id DESC LIMIT 1", (emp["id"],))
        self.assertEqual(lr2["days"], 0.5)
        a.post(f"/staff/leave/{lr2['id']}", data={"action": "disapprove", "note": ""})
        self.assertEqual(self.q("SELECT status FROM leave_requests WHERE id = ?", (lr2["id"],))["status"], "pending")
        a.post(f"/staff/leave/{lr2['id']}", data={"action": "disapprove", "note": "Short staffed that day"})
        self.assertEqual(self.q("SELECT status FROM leave_requests WHERE id = ?", (lr2["id"],))["status"], "disapproved")

    def test_no_self_approval(self):
        from app.util import today
        # an approver (given leave.approve individually) can't approve their own leave
        uid = self.q("SELECT id FROM users WHERE email LIKE 'staff.malolos@%'")["id"]
        self.conn.execute("INSERT OR REPLACE INTO user_permissions (user_id, permission, granted) VALUES (?, 'leave.approve', 1)", (uid,))
        s = self.login("staff.malolos")
        emp = self._emp("staff.malolos")
        self.conn.execute("DELETE FROM leave_requests WHERE employee_id = ?", (emp["id"],))
        d = (today() + timedelta(days=20)).isoformat()
        s.post("/staff/leave/", data={"reliever": "na", "leave_type": "Emergency leave", "start_date": d, "end_date": d, "reason": "Family emergency"})
        lr = self.q("SELECT * FROM leave_requests WHERE employee_id = ? ORDER BY id DESC LIMIT 1", (emp["id"],))
        self.assertEqual(s.post(f"/staff/leave/{lr['id']}", data={"action": "approve"}).status_code, 403)
        self.conn.execute("DELETE FROM user_permissions WHERE user_id = ? AND permission = 'leave.approve'", (uid,))


class TestLeaveWithPay(Base):
    def test_service_incentive_leave_balance(self):
        from app.util import today
        rec = self.login("reception.malolos")
        emp = self.q("SELECT e.* FROM employees e JOIN users u ON u.id = e.user_id WHERE u.email LIKE 'reception.malolos@%'")
        self.conn.execute("UPDATE employees SET employment_type = 'regular', paid_leave_days = NULL WHERE id = ?", (emp["id"],))
        self.conn.execute("DELETE FROM time_records WHERE employee_id = ? AND source = 'leave'", (emp["id"],))
        self.conn.execute("DELETE FROM leave_requests WHERE employee_id = ?", (emp["id"],))
        y = today().year
        # pick Mon–Wed in the future, same year if possible
        from datetime import date, timedelta
        d = max(today() + timedelta(days=3), date(y, 1, 5))
        while d.weekday() != 0:
            d += timedelta(days=1)
        if d.year != y:
            self.skipTest("not enough days left in the year")
        page = rec.get("/staff/leave/").data.decode()
        self.assertIn("SIL, with pay (5 of 5 left)", page)
        rec.post("/staff/leave/", data={"reliever": "na", "leave_type": "Service incentive leave (SIL)", "start_date": d.isoformat(), "end_date": (d + timedelta(days=2)).isoformat(),
                                        "reason": "Rest days"})
        lr = self.q("SELECT * FROM leave_requests WHERE employee_id = ? ORDER BY id DESC LIMIT 1", (emp["id"],))
        self.assertEqual((lr["with_pay"], lr["days"]), (1, 3.0))
        self.assertIn("SIL, with pay (2 of 5 left)", rec.get("/staff/leave/").data.decode())
        # 3 more days with pay is more than the 2 left: refused
        d2 = d + timedelta(days=7)
        rec.post("/staff/leave/", data={"reliever": "na", "leave_type": "Service incentive leave (SIL)", "start_date": d2.isoformat(), "end_date": (d2 + timedelta(days=2)).isoformat(),
                                        "reason": "Flu"})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM leave_requests WHERE employee_id = ?", (emp["id"],))["n"], 1)
        # without pay is fine
        rec.post("/staff/leave/", data={"reliever": "na", "leave_type": "Sick leave", "start_date": d2.isoformat(), "end_date": (d2 + timedelta(days=2)).isoformat(),
                                        "reason": "Flu"})
        self.assertEqual(self.q("SELECT with_pay FROM leave_requests WHERE employee_id = ? ORDER BY id DESC LIMIT 1", (emp["id"],))["with_pay"], 0)
        a = self.login("admin")
        a.post(f"/staff/leave/{lr['id']}", data={"action": "approve"})
        # use up the rest: SIL can't be chosen any more
        d3 = d + timedelta(days=14)
        rec.post("/staff/leave/", data={"reliever": "na", "leave_type": "Service incentive leave (SIL)", "start_date": d3.isoformat(), "end_date": (d3 + timedelta(days=1)).isoformat(), "reason": "Errand"})
        lr3 = self.q("SELECT * FROM leave_requests WHERE employee_id = ? ORDER BY id DESC LIMIT 1", (emp["id"],))
        self.assertEqual(lr3["with_pay"], 1)
        page = rec.get("/staff/leave/").data.decode()
        self.assertIn('value="Service incentive leave (SIL)" disabled', page)
        self.assertIn("no SIL left", page)
        rec.post(f"/staff/leave/{lr3['id']}", data={"action": "cancel"})
        from app.views.leave import balance
        b = balance(self.conn, self.q("SELECT * FROM employees WHERE id = ?", (emp["id"],)))
        self.assertEqual((b["entitled"], b["used"], b["available"]), (5.0, 3.0, 2.0))
        # HR sets a different number for this employee; the balances tab shows it
        a.post(f"/staff/leave/entitlement/{emp['id']}", data={"days": "7"})
        self.assertIn("4", a.get("/staff/leave/?show=balances").data.decode())
        self.assertEqual(balance(self.conn, self.q("SELECT * FROM employees WHERE id = ?", (emp["id"],)))["available"], 4.0)
        self.conn.execute("UPDATE employees SET paid_leave_days = NULL WHERE id = ?", (emp["id"],))


class TestLeaveReliever(Base):
    def test_reliever_lists(self):
        from datetime import timedelta
        from app.util import today
        d = (today() + timedelta(days=40)).isoformat()
        # staff: all employees except dentists, any branch
        rec = self.login("reception.malolos")
        page = rec.get("/staff/leave/").data.decode()
        self.assertIn("Bocaue Receptionist", page)            # another branch
        self.assertNotIn("Dr. Lea Ramos", page.split('id="lrl"')[1].split("</select>")[0])
        self.assertIn("N/A (no one available)", page)
        # a reliever (or N/A) is required
        emp = self.q("SELECT e.* FROM employees e JOIN users u ON u.id = e.user_id WHERE u.email LIKE 'reception.malolos@%'")
        self.conn.execute("DELETE FROM leave_requests WHERE employee_id = ?", (emp["id"],))
        rec.post("/staff/leave/", data={"leave_type": "Vacation leave", "start_date": d, "end_date": d, "reason": "Trip"})
        self.assertIsNone(self.q("SELECT id FROM leave_requests WHERE employee_id = ?", (emp["id"],)))
        other = self.q("SELECT e.id FROM employees e JOIN users u ON u.id = e.user_id WHERE u.email LIKE 'reception.bocaue@%'")["id"]
        rec.post("/staff/leave/", data={"leave_type": "Vacation leave", "start_date": d, "end_date": d, "reason": "Trip", "reliever": str(other)})
        lr = self.q("SELECT * FROM leave_requests WHERE employee_id = ?", (emp["id"],))
        self.assertEqual((lr["reliever_id"], lr["reliever_na"]), (other, 0))
        # a dentist can't be chosen by staff
        dent = self.q("SELECT e.id FROM employees e JOIN users u ON u.id = e.user_id WHERE u.email LIKE 'dentist.sjdm@%'")["id"]
        rec.post("/staff/leave/", data={"leave_type": "Sick leave", "start_date": d, "end_date": d, "reason": "Flu", "reliever": str(dent)})
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM leave_requests WHERE employee_id = ?", (emp["id"],))["n"], 1)
        # dentist: all dentists of any branch, no staff
        doc = self.login("dentist.malolos")
        sel = doc.get("/staff/leave/").data.decode().split('id="lrl"')[1].split("</select>")[0]
        self.assertIn("Dr. Nico Valdez", sel)                   # San Jose del Monte only
        self.assertNotIn("Receptionist", sel)
        self.assertNotIn("Dr. Lea Ramos", sel)                  # not themselves
        # approver sees the reliever; the reliever is notified on approval
        a = self.login("admin")
        self.assertIn("Bocaue Receptionist", a.get("/staff/leave/?show=pending").data.decode())
        a.post(f"/staff/leave/{lr['id']}", data={"action": "approve"})
        ruser = self.q("SELECT user_id FROM employees WHERE id = ?", (other,))["user_id"]
        self.assertTrue(self.q("SELECT id FROM notifications WHERE user_id = ? AND title LIKE 'You are the reliever%'", (ruser,)))
        a.post(f"/staff/leave/{lr['id']}", data={"action": "x"})
        self.conn.execute("DELETE FROM time_records WHERE employee_id = ? AND source = 'leave'", (emp["id"],))
