import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_app import Base  # noqa: E402


class TestIdleSignout(Base):
    def test_user_picks_idle_time_within_the_maximum(self):
        from datetime import timedelta
        from app.util import now
        d = self.login("reception.malolos")
        uid = self.q("SELECT id FROM users WHERE email LIKE 'reception.malolos@%'")["id"]
        page = d.get("/staff/account").data.decode()
        self.assertIn("Sign out when idle", page)
        self.assertIn("4 hours", page)
        d.post("/staff/account/idle", data={"idle_minutes": "240"})
        self.assertEqual(self.q("SELECT idle_minutes FROM users WHERE id = ?", (uid,))["idle_minutes"], 240)
        d.post("/staff/account/idle", data={"idle_minutes": "999"})                    # not a choice
        self.assertEqual(self.q("SELECT idle_minutes FROM users WHERE id = ?", (uid,))["idle_minutes"], 240)
        # 2 hours idle: still signed in with a 4-hour choice
        two_h = (now() - timedelta(minutes=120)).strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute("UPDATE sessions SET last_seen_at = ? WHERE user_id = ?", (two_h, uid))
        self.assertEqual(d.get("/staff/account").status_code, 200)
        # the admin lowers the maximum to 60: the same 2 hours now signs them out
        self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('security.max_idle_minutes', '60')")
        self.conn.execute("UPDATE sessions SET last_seen_at = ? WHERE user_id = ?", (two_h, uid))
        self.assertIn(d.get("/staff/account").status_code, (302, 303))


if __name__ == "__main__":
    unittest.main()
