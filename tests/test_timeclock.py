"""Time clock: selfie + location time in/out feeding the DTR, private photos, retention."""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class TestTimeClock(Base):
    def test_clock_in_out_with_location_and_photo(self):
        bid = self.branch("bocaue")
        self.conn.execute("UPDATE branches SET latitude = 14.8000, longitude = 120.9300, clock_radius_m = 150 WHERE id = ?", (bid,))
        emp = self.q("SELECT e.* FROM employees e JOIN users u ON u.id = e.user_id WHERE u.email = 'reception.bocaue@demo.dentalhaven.test'")
        self.conn.execute("DELETE FROM time_records WHERE employee_id = ?", (emp["id"],))
        c = self.login("reception.bocaue")
        r = c.get("/staff/clock")
        self.assertIn("geolocation=(self)", r.headers["Permissions-Policy"])
        self.assertIn("Time in", r.data.decode())
        # no selfie -> refused
        c.post("/staff/clock", data={"kind": "in", "branch_id": bid, "lat": "14.8001", "lng": "120.9301"})
        self.assertIsNone(self.q("SELECT id FROM time_punches WHERE employee_id = ?", (emp["id"],)))
        c.post("/staff/clock", data={"kind": "in", "branch_id": bid, "lat": "14.8001", "lng": "120.9301", "acc": "12",
                                     "photo": (io.BytesIO(PNG), "selfie.png")}, content_type="multipart/form-data")
        p_in = self.q("SELECT * FROM time_punches WHERE employee_id = ? AND kind = 'in'", (emp["id"],))
        self.assertEqual(p_in["location_ok"], 1)
        self.assertLess(p_in["distance_m"], 30)
        rec = self.q("SELECT * FROM time_records WHERE id = ?", (p_in["time_record_id"],))
        self.assertEqual((rec["source"], rec["time_out"]), ("clock", None))
        self.assertTrue(rec["time_in"])
        # time out ~2 km away: recorded but flagged for review
        c.post("/staff/clock", data={"kind": "out", "branch_id": bid, "lat": "14.8180", "lng": "120.9300", "acc": "10",
                                     "photo": (io.BytesIO(PNG), "selfie.png")}, content_type="multipart/form-data")
        p_out = self.q("SELECT * FROM time_punches WHERE employee_id = ? AND kind = 'out'", (emp["id"],))
        self.assertEqual(p_out["location_ok"], 0)
        rec = self.q("SELECT * FROM time_records WHERE id = ?", (p_in["time_record_id"],))
        self.assertTrue(rec["time_out"])
        self.assertEqual(rec["status"], "exception")
        self.assertIn("m from the branch", rec["exception_note"])
        # a third punch is refused
        c.post("/staff/clock", data={"kind": "out", "branch_id": bid, "photo": (io.BytesIO(PNG), "s.png")}, content_type="multipart/form-data")
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM time_punches WHERE employee_id = ?", (emp["id"],)), 2)
        # selfies: managers only
        self.assertEqual(c.get(f"/staff/clock/photo/{p_in['id']}").status_code, 403)
        admin = self.login("admin")
        self.assertEqual(admin.get(f"/staff/clock/photo/{p_in['id']}").status_code, 200)
        self.assertIn("m away", admin.get("/staff/clock/log").data.decode())
        # retention: old selfies are deleted, the record stays
        self.conn.execute("UPDATE time_punches SET at = '2020-01-01 08:00:00' WHERE id = ?", (p_in["id"],))
        admin.get("/staff/clock/log")
        self.assertIsNone(self.q("SELECT photo FROM time_punches WHERE id = ?", (p_in["id"],))["photo"])
        self.assertEqual(admin.get(f"/staff/clock/photo/{p_in['id']}").status_code, 404)

    def test_setup_branch_location(self):
        admin = self.login("admin")
        bid = self.branch("sjdm")
        admin.post("/staff/clock/settings", data={"branch_id": bid, "lat": "14.8136", "lng": "121.0453", "radius": "120"})
        b = self.q("SELECT latitude, longitude, clock_radius_m FROM branches WHERE id = ?", (bid,))
        self.assertEqual((b["latitude"], b["longitude"], b["clock_radius_m"]), (14.8136, 121.0453, 120))
        r = admin.post("/staff/clock/settings", data={"branch_id": bid, "lat": "abc", "lng": "1", "radius": "120"}, follow_redirects=True)
        self.assertIn("as numbers", r.data.decode())
        self.assertEqual(self.login("reception.sjdm").get("/staff/clock/settings").status_code, 403)

    def test_lab_employee_clocks_in_at_the_lab(self):
        from app.auth import hash_password
        from app.util import now_str
        from test_app import PW
        admin = self.login("admin")
        bid = self.branch("malolos")
        lab = self.conn.insert("laboratories", {"name": "TEST In-house Lab", "active": 1})
        uid = self.conn.insert("users", {"email": "labtech.test@demo.dentalhaven.test", "name": "Lab Tech Test", "password_hash": hash_password(PW),
                                         "role": "staff", "access_role": "technician", "active": 1, "must_change_password": 0,
                                         "created_at": now_str()})
        self.conn.execute("INSERT INTO user_labs (user_id, lab_id) VALUES (?, ?)", (uid, lab))
        emp = self.conn.insert("employees", {"full_name": "Lab Tech Test", "position": "Dental Technician (RPD)", "primary_branch_id": None,
                                             "user_id": uid, "active": 1, "created_at": now_str()})
        tech = self.login("labtech.test")
        # not set up yet: no place to time in
        self.assertIn("no branch or laboratory with a time clock", tech.get("/staff/clock").data.decode())
        # the setup page lists the lab (it has staff); the branch for attendance is required
        page = admin.get("/staff/clock/settings").data.decode()
        self.assertIn("TEST In-house Lab", page)
        r = admin.post("/staff/clock/settings", data={"lab_id": lab, "lat": "14.9000", "lng": "120.8000", "radius": "100"}, follow_redirects=True)
        self.assertIn("handles attendance", r.data.decode())
        admin.post("/staff/clock/settings", data={"lab_id": lab, "lat": "14.9000", "lng": "120.8000", "radius": "100", "lab_branch_id": bid})
        row = self.q("SELECT latitude, longitude, clock_radius_m, branch_id FROM laboratories WHERE id = ?", (lab,))
        self.assertEqual((row["latitude"], row["longitude"], row["clock_radius_m"], row["branch_id"]), (14.9, 120.8, 100, bid))
        # the technician now sees the lab and times in there, checked against the lab's location
        page = tech.get("/staff/clock").data.decode()
        self.assertIn(f'value="l:{lab}" selected', page)
        tech.post("/staff/clock", data={"kind": "in", "place": f"l:{lab}", "lat": "14.9001", "lng": "120.8001", "acc": "10",
                                        "photo": (io.BytesIO(PNG), "selfie.png")}, content_type="multipart/form-data")
        p_in = self.q("SELECT * FROM time_punches WHERE employee_id = ?", (emp,))
        self.assertEqual((p_in["lab_id"], p_in["branch_id"], p_in["location_ok"]), (lab, bid, 1))
        rec = self.q("SELECT * FROM time_records WHERE id = ?", (p_in["time_record_id"],))
        self.assertEqual(rec["branch_id"], bid)
        # can't time out at a branch after timing in at the lab
        self.conn.execute("INSERT INTO user_branches (user_id, branch_id) VALUES (?, ?)", (uid, bid))
        tech = self.login("labtech.test")
        tech.post("/staff/clock", data={"kind": "out", "place": f"b:{bid}", "photo": (io.BytesIO(PNG), "s.png")}, content_type="multipart/form-data")
        self.assertEqual(self.conn.scalar("SELECT COUNT(*) FROM time_punches WHERE employee_id = ?", (emp,)), 1)
        # time out far from the lab: recorded, flagged
        tech.post("/staff/clock", data={"kind": "out", "place": f"l:{lab}", "lat": "14.9200", "lng": "120.8000", "acc": "10",
                                        "photo": (io.BytesIO(PNG), "s.png")}, content_type="multipart/form-data")
        rec = self.q("SELECT * FROM time_records WHERE id = ?", (p_in["time_record_id"],))
        self.assertTrue(rec["time_out"])
        self.assertIn("m from the lab", rec["exception_note"])
        # a lab not assigned to the user can't be used
        other = self.conn.insert("laboratories", {"name": "TEST Other Lab", "active": 1, "branch_id": bid})
        self.assertNotIn("TEST Other Lab", tech.get("/staff/clock").data.decode())
        # the manager's log shows the lab
        log = admin.get("/staff/clock/log").data.decode()
        self.assertIn("TEST In-house Lab", log)
        # clean up
        self.conn.execute("DELETE FROM time_punches WHERE employee_id = ?", (emp,))
        self.conn.execute("DELETE FROM time_records WHERE employee_id = ?", (emp,))
        self.conn.execute("UPDATE employees SET active = 0, user_id = NULL WHERE id = ?", (emp,))
        self.conn.execute("DELETE FROM user_labs WHERE user_id = ?", (uid,))
        self.conn.execute("DELETE FROM user_branches WHERE user_id = ?", (uid,))
        self.conn.execute("UPDATE users SET active = 0 WHERE id = ?", (uid,))
        self.conn.execute("UPDATE laboratories SET active = 0 WHERE id IN (?, ?)", (lab, other))

    def test_field_work_needs_approval_before_it_counts(self):
        from app.auth import hash_password
        from app.payroll import build_lines
        from app.util import now_str, today
        from test_app import PW
        bid = self.branch("bocaue")
        self.conn.execute("UPDATE branches SET latitude = 14.8000, longitude = 120.9300 WHERE id = ?", (bid,))
        emp = self.q("SELECT e.* FROM employees e JOIN users u ON u.id = e.user_id WHERE u.email = 'reception.bocaue@demo.dentalhaven.test'")
        self.conn.execute("DELETE FROM time_punches WHERE employee_id = ?", (emp["id"],))
        self.conn.execute("DELETE FROM time_records WHERE employee_id = ?", (emp["id"],))
        sup = self.conn.insert("users", {"email": "supervisor.field@demo.dentalhaven.test", "name": "Field Supervisor", "password_hash": hash_password(PW),
                                         "role": "staff", "access_role": "supervisor", "active": 1, "must_change_password": 0, "created_at": now_str()})
        self.conn.execute("INSERT INTO user_branches (user_id, branch_id) VALUES (?, ?)", (sup, bid))
        c = self.login("reception.bocaue")
        # a reason is required
        c.post("/staff/clock", data={"kind": "in", "place": f"b:{bid}", "field": "1", "field_reason": "",
                                     "photo": (io.BytesIO(PNG), "s.png")}, content_type="multipart/form-data")
        self.assertIsNone(self.q("SELECT id FROM time_punches WHERE employee_id = ?", (emp["id"],)))
        # far from the branch, but on the field: no distance flag, waits for approval
        c.post("/staff/clock", data={"kind": "in", "place": f"b:{bid}", "field": "1", "field_reason": "Supplier pickup in Manila",
                                     "lat": "14.6000", "lng": "121.0000", "photo": (io.BytesIO(PNG), "s.png")}, content_type="multipart/form-data")
        p = self.q("SELECT * FROM time_punches WHERE employee_id = ?", (emp["id"],))
        self.assertEqual((p["field"], p["field_reason"], p["location_ok"]), (1, "Supplier pickup in Manila", None))
        c.post("/staff/clock", data={"kind": "out", "place": f"b:{bid}", "field": "1", "field_reason": "Still at supplier",
                                     "photo": (io.BytesIO(PNG), "s.png")}, content_type="multipart/form-data")
        rec = self.q("SELECT * FROM time_records WHERE id = ?", (p["time_record_id"],))
        self.assertEqual((rec["field_status"], rec["status"]), ("pending", "exception"))
        self.assertIn("field work (time-in): Supplier pickup in Manila", rec["exception_note"])
        self.assertIn("field work (time-out): Still at supplier", rec["exception_note"])
        self.assertNotIn("m from the branch", rec["exception_note"])
        self.assertIn("Waiting for approval", c.get("/staff/clock").data.decode())
        # the supervisor of that branch is notified
        self.assertTrue(self.q("SELECT id FROM notifications WHERE user_id = ? AND kind = 'field_work'", (sup,)))
        # payroll leaves the day out while it waits
        period = {"branch_id": bid, "start_date": rec["work_date"], "end_date": rec["work_date"]}
        line = next(x for x in build_lines(self.conn, period) if x["employee_id"] == emp["id"])
        self.assertEqual(line["days_present"], 0)
        # the employee can't approve it; the receptionist doesn't even have access
        self.assertEqual(c.post(f"/staff/clock/field/{rec['id']}", data={"action": "approve"}).status_code, 403)
        s = self.login("supervisor.field")
        page = s.get("/staff/clock/log?flag=field").data.decode()
        self.assertIn("Supplier pickup in Manila", page)
        self.assertIn("Approve day", page)
        s.post(f"/staff/clock/field/{rec['id']}", data={"action": "approve", "note": "Confirmed with supplier"})
        rec = self.q("SELECT * FROM time_records WHERE id = ?", (rec["id"],))
        self.assertEqual((rec["field_status"], rec["field_reviewed_by"], rec["field_review_note"]), ("approved", sup, "Confirmed with supplier"))
        self.assertNotIn("field work", rec["exception_note"])
        line = next(x for x in build_lines(self.conn, period) if x["employee_id"] == emp["id"])
        self.assertEqual(line["days_present"], 1)
        self.assertTrue(self.q("SELECT id FROM notifications WHERE user_id = ? AND kind = 'field_work' AND title LIKE 'Field work approved%'",
                               (emp["user_id"],)))
        # declining leaves the day out
        s.post(f"/staff/clock/field/{rec['id']}", data={"action": "decline", "note": "No proof"})
        rec = self.q("SELECT * FROM time_records WHERE id = ?", (rec["id"],))
        self.assertEqual((rec["field_status"], rec["status"]), ("declined", "exception"))
        self.assertIn("field work declined: No proof", rec["exception_note"])
        line = next(x for x in build_lines(self.conn, period) if x["employee_id"] == emp["id"])
        self.assertEqual(line["days_present"], 0)
        # a supervisor can't approve their own field work
        semp = self.conn.insert("employees", {"full_name": "Field Supervisor", "position": "Supervisor", "primary_branch_id": bid,
                                              "user_id": sup, "active": 1, "created_at": now_str()})
        s.post("/staff/clock", data={"kind": "in", "place": f"b:{bid}", "field": "1", "field_reason": "Seminar",
                                     "photo": (io.BytesIO(PNG), "s.png")}, content_type="multipart/form-data")
        srec = self.q("SELECT * FROM time_records WHERE employee_id = ?", (semp,))
        r = s.post(f"/staff/clock/field/{srec['id']}", data={"action": "approve"}, follow_redirects=True)
        self.assertIn("approve your own field work", r.data.decode())
        self.assertEqual(self.q("SELECT field_status FROM time_records WHERE id = ?", (srec["id"],))["field_status"], "pending")
        # clean up
        for e in (emp["id"], semp):
            self.conn.execute("DELETE FROM time_punches WHERE employee_id = ?", (e,))
            self.conn.execute("DELETE FROM time_records WHERE employee_id = ?", (e,))
        self.conn.execute("UPDATE employees SET active = 0, user_id = NULL WHERE id = ?", (semp,))
        self.conn.execute("UPDATE users SET active = 0 WHERE id = ?", (sup,))
