"""Group chat: everyone posts and reads; text only; remove own (moderators any); unread count; old messages purged."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_payroll_rules import TestPayrollRules  # noqa: E402


class TestChat(TestPayrollRules):
    for _n in [n for n in dir(TestPayrollRules) if n.startswith("test_")]:
        locals()[_n] = None

    def test_group_chat(self):
        rec = self.login("reception.malolos")
        admin = self.login("admin")
        self.assertEqual(rec.get("/staff/chat/").status_code, 200)
        rec.post("/staff/chat/", data={"body": "Good morning team <b>hi</b>"})
        m = self.q("SELECT * FROM chat_messages ORDER BY id DESC LIMIT 1")
        self.assertEqual(m["body"], "Good morning team <b>hi</b>")
        page = admin.get("/staff/").data.decode()
        self.assertIn('Group chat</span><span class="count">', page)          # unread for the other person
        chat = admin.get("/staff/chat/").data.decode()
        self.assertIn("Good morning team &lt;b&gt;hi&lt;/b&gt;", chat)        # escaped, shown as text
        self.assertNotIn('Group chat</span><span class="count">', admin.get("/staff/").data.decode())
        # JSON polling and sending
        r = admin.post("/staff/chat/", data={"body": "Noted"}, headers={"Accept": "application/json"})
        self.assertTrue(r.get_json()["ok"])
        got = rec.get(f"/staff/chat/since?after={m['id']}").get_json()
        self.assertEqual([x["body"] for x in got["messages"]], ["Noted"])
        self.assertEqual(rec.post("/staff/chat/", data={"body": ""}, headers={"Accept": "application/json"}).status_code, 400)
        self.assertEqual(rec.post("/staff/chat/", data={"body": "x" * 1001}, headers={"Accept": "application/json"}).status_code, 400)
        # remove: not someone else's (unless moderator), yes own
        other = r.get_json()["id"]
        self.assertEqual(rec.post(f"/staff/chat/{other}/remove").status_code, 403)
        rec.post(f"/staff/chat/{m['id']}/remove")
        gone = self.q("SELECT * FROM chat_messages WHERE id = ?", (m["id"],))
        self.assertEqual((gone["body"], bool(gone["deleted_at"])), ("", True))
        got = rec.get(f"/staff/chat/since?after={other}&first={m['id']}").get_json()
        self.assertIn(m["id"], got["removed"])
        admin.post(f"/staff/chat/{other}/remove")
        self.assertIsNotNone(self.q("SELECT deleted_at FROM chat_messages WHERE id = ?", (other,))["deleted_at"])
        # messages older than a year are deleted
        self.conn.execute("INSERT INTO chat_messages (user_id, body, created_at) VALUES (?, 'old', '2000-01-01 08:00:00')",
                          (self.q("SELECT id FROM users WHERE role = 'super_admin' LIMIT 1")["id"],))
        admin.get("/staff/chat/")
        self.assertIsNone(self.q("SELECT id FROM chat_messages WHERE body = 'old'"))


del TestPayrollRules
