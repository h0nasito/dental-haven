"""Clinic & lab overview: who can open it, and that the numbers come out."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestOverview(Base):
    def test_admin_sees_overview(self):
        c = self.login("admin")
        for q in ("", "?period=week", "?period=month", "?period=year"):
            r = c.get(f"/staff/overview{q}")
            self.assertEqual(r.status_code, 200, r.data[:800])
            page = r.data.decode()
            for text in ("Clinic ", "Laboratory", "Collected", "Unpaid bills", "Open lab work", "<svg class=\"ov-chart\""):
                self.assertIn(text, page)
        self.assertIn("Clinic &amp; lab overview", c.get("/staff/").data.decode())

    def test_numbers_match_the_data(self):
        from datetime import date
        from app import overview as ov
        with self.app.app_context():
            from app.db import get_db
            conn = get_db()
            ids = [r["id"] for r in conn.all("SELECT id FROM branches")]
            d = ov.build(conn, ids, date.today())
            day = date.today().isoformat()
            n = conn.scalar("SELECT COUNT(*) FROM appointments WHERE substr(start_at, 1, 10) = ? AND status != 'cancelled'", (day,))
            self.assertEqual(d["appts"]["all"][0], n)
            self.assertEqual(len(d["chart_labels"]), 14)
            self.assertEqual(len(ov.build(conn, ids, date.today(), "year")["chart_labels"]), 12)

    def test_dentist_cannot_open(self):
        self.assertEqual(self.login("dentist.malolos").get("/staff/overview").status_code, 403)


class TestFinancialSummary(Base):
    def test_daily_monthly_yearly(self):
        c = self.login("admin")
        for by, word in (("day", "Summary by day"), ("month", "Summary by month"), ("year", "Summary by year")):
            r = c.get(f"/staff/reports/financial?from=2026-01-01&to=2026-10-23&by={by}")
            self.assertEqual(r.status_code, 200)
            self.assertIn(word, r.data.decode())
        page = c.get("/staff/reports/financial?from=2026-01-01&to=2026-03-31&by=month").data.decode()
        for m in ("January 2026", "February 2026", "March 2026"):
            self.assertIn(m, page)
        self.assertIn("This year", page)
        csv_ = c.get("/staff/reports/financial?from=2026-01-01&to=2026-03-31&by=month&format=csv").data.decode("utf-8-sig")
        self.assertIn("Summary by month", csv_)
