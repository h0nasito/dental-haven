"""The new-booking chime endpoint: permissions, branch scope, no personal data."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestBookingPulse(Base):
    URL = "/staff/requests/pulse.json"

    def add_request(self, slug, name):
        b = self.branch(slug)
        svc = self.q("SELECT id FROM services LIMIT 1")["id"]
        day = self.next_weekday(1)
        return self.conn.insert("booking_requests", {
            "ref_code": f"DH-PULSE{os.urandom(3).hex()}", "full_name": name, "phone": "0900 000 0000", "email": "",
            "branch_id": b, "service_id": svc, "preferred_start": f"{day.isoformat()} 10:00",
            "message": "synthetic", "consent_privacy": 1, "consent_contact": 1, "status": "pending",
            "created_at": f"{day.isoformat()} 08:00:00"})

    def test_reception_gets_counts_for_own_branch_only(self):
        c = self.login("reception.malolos")
        before = c.get(self.URL).get_json()
        rid = self.add_request("malolos", "Pulse Synthetic Malolos")
        after = c.get(self.URL)
        self.assertEqual(after.status_code, 200)
        self.assertEqual(after.headers.get("Cache-Control"), "no-store")
        j = after.get_json()
        self.assertEqual(j["latest"], rid)
        self.assertEqual(j["count"], before["count"] + 1)
        self.assertNotIn(b"Pulse Synthetic", after.data)
        self.assertNotIn(b"0900", after.data)
        since = c.get(f"{self.URL}?after={before['latest']}").get_json()
        self.assertEqual(since["new"], 1)
        self.assertEqual(since["branches"], ["Malolos"])
        self.assertEqual(c.get(f"{self.URL}?after={rid}").get_json()["new"], 0)
        other = self.add_request("sjdm", "Pulse Synthetic SJDM")
        self.assertEqual(c.get(self.URL).get_json()["latest"], rid)
        self.assertLess(rid, other)

    def tech(self):
        from app.auth import hash_password
        from app.util import now_str
        from test_app import PW
        if not self.q("SELECT id FROM users WHERE email = 'pulsetech.test@demo.dentalhaven.test'"):
            self.conn.insert("users", {"email": "pulsetech.test@demo.dentalhaven.test", "name": "Pulse Tech Test",
                                       "password_hash": hash_password(PW), "role": "staff", "access_role": "technician",
                                       "active": 1, "must_change_password": 0, "created_at": now_str()})
        return self.login("pulsetech.test")

    def test_people_without_booking_access_are_refused(self):
        self.assertIn(self.tech().get(self.URL).status_code, (302, 403))

    def test_passive_check_leaves_last_seen_untouched(self):
        c = self.login("reception.malolos")
        uid = self.q("SELECT id FROM users WHERE email = 'reception.malolos@demo.dentalhaven.test'")["id"]
        from app.util import now_str
        mark = now_str()
        self.conn.execute("UPDATE sessions SET last_seen_at = ? WHERE user_id = ?", (mark, uid))
        import time
        time.sleep(1.1)
        self.assertEqual(c.get(self.URL).status_code, 200)
        self.assertEqual(self.q("SELECT MAX(last_seen_at) AS t FROM sessions WHERE user_id = ?", (uid,))["t"], mark)
        c.get("/staff/requests")
        self.assertNotEqual(self.q("SELECT MAX(last_seen_at) AS t FROM sessions WHERE user_id = ?", (uid,))["t"], mark)

    def test_toggle_only_for_booking_staff(self):
        page = self.login("reception.malolos").get("/staff/requests").data
        self.assertIn(b'id="req-sound"', page)
        self.assertNotIn(b"data-lab-pulse", page)
        page = self.tech().get("/staff/clock")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'id="req-sound"', page.data)


class TestLabPulse(Base):
    URL = "/staff/lab/pulse.json"

    def setUp(self):
        from app.auth import hash_password
        from app.util import now_str
        from test_app import PW
        self.lab = self.q("SELECT id FROM laboratories WHERE name = 'PULSE Test Lab'")
        self.lab = self.lab["id"] if self.lab else self.conn.insert("laboratories", {"name": "PULSE Test Lab", "active": 1})
        if not self.q("SELECT id FROM users WHERE email = 'pulselab.test@demo.dentalhaven.test'"):
            uid = self.conn.insert("users", {"email": "pulselab.test@demo.dentalhaven.test", "name": "Pulse Lab Test",
                                             "password_hash": hash_password(PW), "role": "staff", "access_role": "technician",
                                             "active": 1, "must_change_password": 0, "created_at": now_str()})
            self.conn.execute("INSERT INTO user_labs (user_id, lab_id) VALUES (?, ?)", (uid, self.lab))
        self.uid = self.q("SELECT id FROM users WHERE email = 'pulselab.test@demo.dentalhaven.test'")["id"]

    def add_case(self, lab, created_by=None):
        from app.util import now_str
        p = self.q("SELECT id FROM patients LIMIT 1")["id"]
        return self.conn.insert("lab_cases", {"lab_id": lab, "branch_id": self.branch("malolos"), "patient_id": p,
                                              "case_type": "PFM Crown", "status": "sent", "sent_on": "2026-10-26",
                                              "due_on": "2026-11-02", "created_by": created_by, "created_at": now_str()})

    def test_lab_staff_hear_new_cases_for_their_lab_only(self):
        c = self.login("pulselab.test")
        page = c.get("/staff/clock").data
        self.assertIn(b"data-lab-pulse", page)
        self.assertNotIn(b'data-pulse="', page)
        start = c.get(self.URL).get_json()["latest"]
        mine = self.add_case(self.lab, created_by=self.q("SELECT id FROM users WHERE email LIKE 'dentist.malolos%'")["id"])
        other_lab = self.conn.insert("laboratories", {"name": "PULSE Other Lab", "active": 1})
        self.add_case(other_lab)
        j = c.get(f"{self.URL}?after={start}").get_json()
        self.assertEqual(j["latest"], mine)
        self.assertEqual(j["new"], 1)
        self.assertEqual(j["branches"], ["Malolos"])
        self.assertIn("PFM Crown", j["label"])
        raw = c.get(f"{self.URL}?after={start}").data
        pt = self.q("SELECT first_name, last_name FROM patients LIMIT 1")
        self.assertNotIn(pt["last_name"].encode(), raw)

    def test_own_entry_does_not_alert(self):
        c = self.login("pulselab.test")
        start = c.get(self.URL).get_json()["latest"]
        self.add_case(self.lab, created_by=self.uid)
        self.assertEqual(c.get(f"{self.URL}?after={start}").get_json()["new"], 0)

    def test_people_not_in_a_lab_are_refused(self):
        self.assertEqual(self.login("reception.malolos").get(self.URL).status_code, 403)
