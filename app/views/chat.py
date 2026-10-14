"""Staff group chat: one chat for everyone, text only (no pictures or files), no private messages.

- Everyone signed in to the staff side can read and post.
- People can remove their own messages; HR / supervisors / the super admin (announcements.manage) can remove any message
  and pin or unpin messages (pinned ones stay at the top of the chat).
- An emoji button helps type emoticons.
- Messages older than a year are deleted automatically.
- Message text is never written to logs, notifications or the audit trail.
"""
from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from .. import audit
from ..auth import login_required
from ..db import get_db
from ..jinja import _dt
from ..notices import notify
from ..util import now, now_str, to_int

bp = Blueprint("chat", __name__, url_prefix="/staff/chat")

KEEP_DAYS = 365
MAX_LEN = 1000
PAGE = 80
RATE = 15   # messages a minute per person


def purge_old(conn) -> int:
    cutoff = (now() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    return conn.execute("DELETE FROM chat_messages WHERE created_at < ?", (cutoff,)).rowcount


def unread(conn, user_id: int) -> int:
    last = conn.scalar("SELECT last_read_id FROM chat_reads WHERE user_id = ?", (user_id,)) or 0
    return conn.scalar("SELECT COUNT(*) FROM chat_messages WHERE id > ? AND user_id != ? AND deleted_at IS NULL", (last, user_id)) or 0


def _mark_read(conn, upto: int):
    if upto:
        conn.execute("INSERT INTO chat_reads (user_id, last_read_id) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET "
                     "last_read_id = MAX(last_read_id, excluded.last_read_id)", (g.user.id, upto))


def _moderator() -> bool:
    return g.user.is_super_admin or g.user.can("announcements.manage")


def _can_remove(m) -> bool:
    return m["user_id"] == g.user.id or _moderator()


MAX_PINS = 10


def pinned(conn) -> list[dict]:
    rows = conn.all(SELECT + "WHERE m.pinned_at IS NOT NULL AND m.deleted_at IS NULL ORDER BY m.pinned_at DESC LIMIT ?", (MAX_PINS,))
    return [_as_dict(m) for m in rows]


def _as_dict(m) -> dict:
    return {"id": m["id"], "name": m["name"], "role": m["position"] or "", "mine": m["user_id"] == g.user.id,
            "when": _dt(m["created_at"], "%b %d, %I:%M %p"), "day": m["created_at"][:10],
            "body": "" if m["deleted_at"] else m["body"], "removed": bool(m["deleted_at"]),
            "can_remove": not m["deleted_at"] and _can_remove(m),
            "pinned": bool(m["pinned_at"]) and not m["deleted_at"], "can_pin": not m["deleted_at"] and _moderator(),
            "reply": _reply(m)}


def _reply(m):
    if not m["reply_to_id"]:
        return None
    if m["r_name"] is None:          # the original was deleted (older than a year)
        return {"id": None, "name": "", "mine": False, "text": "Original message is no longer available", "removed": True}
    removed = bool(m["r_deleted"])
    return {"id": m["reply_to_id"], "name": m["r_name"], "mine": m["r_user"] == g.user.id,
            "text": "Message removed" if removed else _snippet(m["r_body"]), "removed": removed}


SELECT = ("SELECT m.*, u.name, e.position, r.body AS r_body, r.deleted_at AS r_deleted, r.user_id AS r_user, ru.name AS r_name "
          "FROM chat_messages m JOIN users u ON u.id = m.user_id LEFT JOIN employees e ON e.user_id = m.user_id "
          "LEFT JOIN chat_messages r ON r.id = m.reply_to_id LEFT JOIN users ru ON ru.id = r.user_id ")


def _snippet(text: str, n: int = 90) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


@bp.route("/")
@login_required
def index():
    conn = get_db()
    with conn.transaction():
        purge_old(conn)
    before = to_int(request.args.get("before"))
    if before:
        rows = conn.all(SELECT + "WHERE m.id < ? ORDER BY m.id DESC LIMIT ?", (before, PAGE))
    else:
        rows = conn.all(SELECT + "ORDER BY m.id DESC LIMIT ?", (PAGE,))
    msgs = [_as_dict(m) for m in reversed(rows)]
    older = bool(msgs) and bool(conn.scalar("SELECT COUNT(*) FROM chat_messages WHERE id < ?", (msgs[0]["id"],)))
    last = conn.scalar("SELECT MAX(id) FROM chat_messages") or 0
    if not before:
        with conn.transaction():
            _mark_read(conn, last)
    people = conn.scalar("SELECT COUNT(*) FROM users WHERE active = 1")
    replying = None
    rid = to_int(request.args.get("reply"))
    if rid:
        r = conn.one(SELECT + "WHERE m.id = ? AND m.deleted_at IS NULL", (rid,))
        if r:
            replying = {"id": r["id"], "name": "You" if r["user_id"] == g.user.id else r["name"], "text": _snippet(r["body"])}
    return render_template("staff/chat/index.html", pins=pinned(conn), emojis=EMOJIS, msgs=msgs, older=older, last=last, before=before, people=people,
                           keep_days=KEEP_DAYS, max_len=MAX_LEN, replying=replying)


@bp.route("/since")
@login_required
def since():
    """New messages after an id (the page asks every few seconds), plus ids removed since then."""
    conn = get_db()
    after = to_int(request.args.get("after"), 0)
    rows = conn.all(SELECT + "WHERE m.id > ? ORDER BY m.id LIMIT 200", (after,))
    first = to_int(request.args.get("first"), after)
    removed = [r["id"] for r in conn.all("SELECT id FROM chat_messages WHERE id >= ? AND id <= ? AND deleted_at IS NOT NULL",
                                         (first, after))]
    if rows:
        with conn.transaction():
            _mark_read(conn, rows[-1]["id"])
    pin_ids = [r["id"] for r in conn.all("SELECT id FROM chat_messages WHERE pinned_at IS NOT NULL AND deleted_at IS NULL AND id >= ?", (first,))]
    return jsonify(messages=[_as_dict(m) for m in rows], removed=removed, pins=pinned(conn), pinned_ids=pin_ids)


@bp.route("/", methods=["POST"])
@login_required
def post():
    conn = get_db()
    body = (request.form.get("body") or "").strip()
    wants_json = request.headers.get("Accept", "").startswith("application/json")
    error = None
    if not body:
        error = "Write a message first."
    elif len(body) > MAX_LEN:
        error = f"Messages can be up to {MAX_LEN} characters."
    else:
        minute_ago = (now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
        if conn.scalar("SELECT COUNT(*) FROM chat_messages WHERE user_id = ? AND created_at >= ?", (g.user.id, minute_ago)) >= RATE:
            error = "You're sending messages too fast. Wait a minute."
    if error:
        if wants_json:
            return jsonify(error=error), 400
        flash(error, "error")
        return redirect(url_for("chat.index"))
    reply_to = to_int(request.form.get("reply_to"))
    target = conn.one("SELECT id, user_id FROM chat_messages WHERE id = ? AND deleted_at IS NULL", (reply_to,)) if reply_to else None
    with conn.transaction():
        mid = conn.insert("chat_messages", {"user_id": g.user.id, "body": body, "created_at": now_str(),
                                            "reply_to_id": target["id"] if target else None})
        _mark_read(conn, mid)
        if target and target["user_id"] != g.user.id:
            # no message text in the notification
            notify(conn, [target["user_id"]], "chat_reply", f"{g.user.name} replied to your message in the group chat", "",
                   url_for("chat.index") + f"#m{mid}")
    if wants_json:
        return jsonify(ok=True, id=mid)
    return redirect(url_for("chat.index") + "#bottom")


@bp.route("/<int:mid>/remove", methods=["POST"])
@login_required
def remove(mid):
    conn = get_db()
    m = conn.one("SELECT * FROM chat_messages WHERE id = ?", (mid,))
    if not m:
        abort(404)
    if not _can_remove(m):
        abort(403)
    if not m["deleted_at"]:
        with conn.transaction():
            conn.execute("UPDATE chat_messages SET body = '', deleted_at = ?, deleted_by = ?, pinned_at = NULL, pinned_by = NULL WHERE id = ?",
                         (now_str(), g.user.id, mid))
            if m["user_id"] != g.user.id:
                audit.record("chat.remove", "chat_message", mid, "Removed a group chat message by another user")
    if request.headers.get("Accept", "").startswith("application/json"):
        return jsonify(ok=True)
    return redirect(url_for("chat.index"))


@bp.route("/<int:mid>/pin", methods=["POST"])
@login_required
def pin(mid):
    """Pin or unpin a message (admin, HR, supervisors)."""
    if not _moderator():
        abort(403)
    conn = get_db()
    m = conn.one("SELECT * FROM chat_messages WHERE id = ?", (mid,))
    if not m or m["deleted_at"]:
        abort(404)
    with conn.transaction():
        if m["pinned_at"]:
            conn.execute("UPDATE chat_messages SET pinned_at = NULL, pinned_by = NULL WHERE id = ?", (mid,))
        else:
            conn.execute("UPDATE chat_messages SET pinned_at = ?, pinned_by = ? WHERE id = ?", (now_str(), g.user.id, mid))
            # keep at most MAX_PINS: the oldest pin drops off
            conn.execute("UPDATE chat_messages SET pinned_at = NULL, pinned_by = NULL WHERE id IN (SELECT id FROM chat_messages "
                         "WHERE pinned_at IS NOT NULL AND deleted_at IS NULL ORDER BY pinned_at DESC, id DESC LIMIT -1 OFFSET ?)", (MAX_PINS,))
    if request.headers.get("Accept", "").startswith("application/json"):
        return jsonify(ok=True, pinned=not m["pinned_at"], pins=pinned(conn))
    return redirect(url_for("chat.index"))


EMOJIS = ["😀", "😁", "😂", "🤣", "😊", "😍", "🥰", "😘", "😉", "😎", "🤗", "🤔", "😅", "😆", "🙂", "🙃", "😇", "🥳", "😴", "😢",
          "😭", "😮", "😱", "😡", "😬", "🙄", "🤦", "🤷", "🙏", "👍", "👎", "👏", "🙌", "👌", "✌️", "💪", "👋", "🤝", "❤️", "💙",
          "💚", "💛", "🔥", "✨", "🎉", "🎂", "🎁", "☕", "🍔", "🍕", "🦷", "🪥", "😷", "💉", "📅", "⏰", "✅", "❌", "⚠️", "📌",
          "📢", "💯", "⭐", "🌞", "🌧️", "🏥", "🚗", "💰"]
