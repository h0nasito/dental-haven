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
        # pin: only the admin / HR / supervisors; pinned shows at the top and in polling
        self.assertEqual(rec.post(f"/staff/chat/{m['id']}/pin").status_code, 403)
        pr = admin.post(f"/staff/chat/{m['id']}/pin", headers={"Accept": "application/json"}).get_json()
        self.assertTrue(pr["pinned"])
        self.assertEqual([p["id"] for p in pr["pins"]], [m["id"]])
        self.assertIn("📌 Pinned", rec.get("/staff/chat/").data.decode())
        self.assertIn(m["id"], rec.get(f"/staff/chat/since?after={m['id']}&first={m['id']}").get_json()["pinned_ids"])
        self.assertIn("😊", rec.get("/staff/chat/").data.decode())                # emoticon button
        other = r.get_json()["id"]
        # reply: quotes the original, notifies its author (without the message text)
        rr = rec.post("/staff/chat/", data={"body": "Yes, see you", "reply_to": str(other)}, headers={"Accept": "application/json"}).get_json()
        rep = self.q("SELECT * FROM chat_messages WHERE id = ?", (rr["id"],))
        self.assertEqual(rep["reply_to_id"], other)
        got = admin.get(f"/staff/chat/since?after={other}").get_json()["messages"][-1]
        self.assertEqual((got["reply"]["id"], got["reply"]["text"]), (other, "Noted"))
        admin_id = self.q("SELECT user_id FROM chat_messages WHERE id = ?", (other,))["user_id"]
        n = self.q("SELECT * FROM notifications WHERE user_id = ? AND kind = 'chat_reply' ORDER BY id DESC LIMIT 1", (admin_id,))
        self.assertIn("replied to your message", n["title"])
        self.assertNotIn("see you", (n["title"] + n["body"]).lower())
        self.assertIn("Replying to", rec.get(f"/staff/chat/?reply={other}").data.decode())
        # @mention: highlighted and the mentioned person is notified (no message text)
        admin_name = self.q("SELECT name FROM users WHERE id = ?", (admin_id,))["name"]
        mm = rec.post("/staff/chat/", data={"body": f"Hi @{admin_name}, please check"}, headers={"Accept": "application/json"}).get_json()
        n = self.q("SELECT * FROM notifications WHERE user_id = ? AND kind = 'chat_mention' ORDER BY id DESC LIMIT 1", (admin_id,))
        self.assertIn("mentioned you", n["title"])
        self.assertNotIn("please check", n["title"] + n["body"])
        got = admin.get(f"/staff/chat/since?after={mm['id'] - 1}").get_json()["messages"][-1]
        self.assertTrue(got["mentions_me"])
        self.assertIn({"t": "@" + admin_name, "m": True, "me": True}, got["parts"])
        self.assertIn('class="mention me"', admin.get("/staff/chat/").data.decode())
        # remove: not someone else's (unless moderator), yes own
        self.assertEqual(rec.post(f"/staff/chat/{other}/remove").status_code, 403)
        rec.post(f"/staff/chat/{m['id']}/remove")
        gone = self.q("SELECT * FROM chat_messages WHERE id = ?", (m["id"],))
        self.assertEqual((gone["body"], bool(gone["deleted_at"])), ("", True))
        got = rec.get(f"/staff/chat/since?after={other}&first={m['id']}").get_json()
        self.assertIn(m["id"], got["removed"])
        self.assertEqual(got["pins"], [])                                       # a removed message is unpinned
        admin.post(f"/staff/chat/{other}/remove")
        msgs = admin.get(f"/staff/chat/since?after={other}").get_json()["messages"]
        self.assertEqual(next(x for x in msgs if x["id"] == rr["id"])["reply"]["text"], "Message removed")
        self.assertIsNotNone(self.q("SELECT deleted_at FROM chat_messages WHERE id = ?", (other,))["deleted_at"])
        # messages older than a year are deleted
        self.conn.execute("INSERT INTO chat_messages (user_id, body, created_at) VALUES (?, 'old', '2000-01-01 08:00:00')",
                          (self.q("SELECT id FROM users WHERE role = 'super_admin' LIMIT 1")["id"],))
        admin.get("/staff/chat/")
        self.assertIsNone(self.q("SELECT id FROM chat_messages WHERE body = 'old'"))


del TestPayrollRules
