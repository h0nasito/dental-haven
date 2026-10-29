"""Monthly tithe: a share of last month's net profit (Monthly business report), emailed to the daily report recipients."""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_app import Base  # noqa: E402


class TestTithe(Base):
    def test_build_text_and_schedule(self):
        from app import settings, tithe
        from app.business_report import figures, month_bounds
        c = self.conn
        month = date(2026, 9, 1)
        with self.app.app_context():
            t = tithe.build(c, month)
            s, e = month_bounds(month)
            net = figures(c, [dict(b) for b in c.all("SELECT * FROM branches WHERE active = 1")], s, e)["net"]
            self.assertEqual(t["net"], net)
            self.assertEqual(t["tithe"], max(0, round(net * 10 / 100)))
            text = tithe.as_text(t)
            self.assertIn("Tithe for September 2026", text)
            self.assertIn("10% of net profit", text)
            # schedule: off by default; on, it sends last month once on the set day (demo/test mode never emails)
            sent = []
            with mock.patch.object(tithe, "send", lambda conn, m: sent.append(m)):
                self.assertFalse(tithe.run(c))
                settings.put("report.tithe_enabled", True, None, c)
                settings.put("report.tithe_last_month", "2026-08", None, c)
                with mock.patch.object(tithe, "now", return_value=datetime(2026, 10, 4, 23, 30)):
                    self.assertFalse(tithe.run(c))                    # before the 5th
                with mock.patch.object(tithe, "now", return_value=datetime(2026, 10, 5, 22, 0)):
                    self.assertFalse(tithe.run(c))                    # before the daily report time
                with mock.patch.object(tithe, "now", return_value=datetime(2026, 10, 5, 23, 5)):
                    self.assertTrue(tithe.run(c))
                    self.assertFalse(tithe.run(c))                    # once
                self.assertEqual(sent, [date(2026, 9, 1)])
                # turned on for the first time after the send day: starts with next month, nothing old is sent
                settings.put("report.tithe_last_month", None, None, c)
                c.execute("DELETE FROM settings WHERE key = 'report.tithe_last_month'")
                with mock.patch.object(tithe, "now", return_value=datetime(2026, 10, 29, 23, 5)):
                    self.assertFalse(tithe.run(c))
                self.assertEqual(len(sent), 1)
            settings.put("report.tithe_enabled", False, None, c)
            self.assertEqual(tithe.send(c, month, ["owner@example.com"])[0], 0)   # tests never send

    def test_business_report_and_settings(self):
        a = self.login("admin")
        self.assertIn("Tithe (10% of net profit)", a.get("/staff/reports/business").data.decode())
        page = a.get("/staff/admin/system").data.decode()
        self.assertIn("monthly tithe", page)
