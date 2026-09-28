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
