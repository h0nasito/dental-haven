"""Chairs per branch: one dentist per chair, so several dentists can work at the same time."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import DOMAIN, Base  # noqa: E402


class TestChairs(Base):
    def test_chair_counts_per_branch(self):
        counts = {r["slug"]: r["n"] for r in self.conn.all(
            "SELECT b.slug, COUNT(r.id) AS n FROM branches b JOIN resources r ON r.branch_id = b.id AND r.kind = 'chair' "
            "AND r.active = 1 GROUP BY b.slug")}
        self.assertEqual(counts, {"malolos": 5, "guiguinto": 3, "bocaue": 2, "sjdm": 2})

    def test_top_up_only_adds(self):
        from app.seed import seed_base
        sjdm = self.branch("sjdm")
        chair = self.q("SELECT id FROM resources WHERE branch_id = ? ORDER BY id LIMIT 1", (sjdm,))["id"]
        self.conn.execute("UPDATE resources SET active = 0 WHERE id = ?", (chair,))  # staff switch one off
        try:
            seed_base(self.conn)  # runs on every start of the live site
            self.assertEqual(self.q("SELECT COUNT(*) AS n FROM resources WHERE branch_id = ?", (sjdm,))["n"], 2)
            self.assertEqual(self.q("SELECT active FROM resources WHERE id = ?", (chair,))["active"], 0)
        finally:
            self.conn.execute("UPDATE resources SET active = 1 WHERE id = ?", (chair,))

    def test_two_dentists_same_time_different_chairs(self):
        c = self.login("reception.malolos")
        malolos = self.branch("malolos")
        svc = self.q("SELECT id FROM services WHERE slug='general-dentistry'")["id"]
        d1 = self.q("SELECT id FROM users WHERE email = ?", ("dentist.malolos" + DOMAIN,))["id"]
        d2 = self.q("SELECT id FROM users WHERE email = ?", ("dentist.bocaue" + DOMAIN,))["id"]
        pats = self.conn.all("SELECT id FROM patients WHERE preferred_branch_id = ? LIMIT 3", (malolos,))
        day = self.next_weekday(3, weeks=15)
        # in the demo data the second dentist isn't at Malolos on Thursdays; give them a shift there for this test
        sid = self.conn.insert("dentist_schedules", {"dentist_id": d2, "branch_id": malolos, "weekday": 3,
                                                     "start_time": "09:00", "end_time": "17:00"})
        self.addCleanup(self.conn.execute, "DELETE FROM dentist_schedules WHERE id = ?", (sid,))
        form = {"branch_id": malolos, "service_id": svc, "date": day.isoformat(), "time": "10:00", "status": "confirmed", "source": "phone"}
        for pid, did in ((pats[0]["id"], d1), (pats[1]["id"], d2)):
            r = c.post("/staff/appointments/new", data=dict(form, patient_id=pid, dentist_id=did))
            self.assertEqual(r.status_code, 302, [l for l in r.data.decode().splitlines() if 'error' in l.lower()][:5])
        rows = self.conn.all("SELECT dentist_id, resource_id FROM appointments WHERE branch_id = ? AND start_at = ? AND status = 'confirmed'",
                             (malolos, f"{day} 10:00"))
        self.assertEqual({r["dentist_id"] for r in rows}, {d1, d2})
        self.assertEqual(len({r["resource_id"] for r in rows}), 2)  # each on their own chair
        # the same dentist can't take a second patient at that time, even with chairs free
        r = c.post("/staff/appointments/new", data=dict(form, patient_id=pats[2]["id"], dentist_id=d1))
        self.assertIn(b"Conflict", r.data)
        # choosing a chair that's already taken is refused
        taken = rows[0]["resource_id"]
        r = c.post("/staff/appointments/new", data=dict(form, patient_id=pats[2]["id"], dentist_id="", resource_id=taken))
        self.assertIn(b"in use", r.data)
        # chair view of the calendar shows one column per chair
        page = c.get(f"/staff/calendar?view=chairs&date={day}").data
        self.assertIn(b"Chair 5", page)
        self.assertIn(b"One dentist per chair", page)
