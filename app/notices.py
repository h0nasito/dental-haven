"""In-app notifications for staff (the bell in the top bar). Nothing here leaves the system.

Notifications never contain patient names or other patient details: they name the case number,
the case type and the sending clinic or branch, and link to the page where authorised users see more.
"""
from __future__ import annotations

from datetime import timedelta

from . import settings
from .util import now_str, today


def notify(conn, user_ids, kind: str, title: str, body: str = "", link: str = "", exclude=None):
    ids = sorted({u for u in user_ids if u and u != exclude})
    for uid in ids:
        conn.insert("notifications", {"user_id": uid, "kind": kind, "title": title[:200], "body": body[:500], "link": link[:300],
                                      "created_at": now_str()})
    return len(ids)


def lab_staff(conn, lab_id: int) -> list[int]:
    """Active users assigned to the lab (they handle its work)."""
    return [r["user_id"] for r in conn.all(
        "SELECT ul.user_id FROM user_labs ul JOIN users u ON u.id = ul.user_id WHERE ul.lab_id = ? AND u.active = 1", (lab_id,))]


def unread_count(conn, user_id: int) -> int:
    return conn.scalar("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read_at IS NULL", (user_id,)) or 0


def run_lab_due_checks(conn):
    """Once a day: 'due tomorrow' and 'overdue' notices for outside-clinic works and branch lab cases. Safe to call often."""
    day = today().isoformat()
    if settings.get("notify.lab_due_checked", conn) == day:
        return
    settings.put("notify.lab_due_checked", day, None, conn)
    tomorrow = (today() + timedelta(days=1)).isoformat()
    from .lab_status import LATE, sql_list
    open_works = sql_list(LATE)
    for w in conn.all(f"SELECT * FROM lab_works WHERE status IN {open_works} AND due_on = ? AND due_soon_notified = 0", (tomorrow,)):
        notify(conn, lab_staff(conn, w["lab_id"]), "lab_due", f"Due tomorrow: {w['number']}",
               f"{w['case_type']} for {w['clinic_name']}", f"/staff/lab/works/{w['id']}")
        conn.execute("UPDATE lab_works SET due_soon_notified = 1 WHERE id = ?", (w["id"],))
    for w in conn.all(f"SELECT * FROM lab_works WHERE status IN {open_works} AND due_on < ? AND overdue_notified = 0", (day,)):
        notify(conn, lab_staff(conn, w["lab_id"]), "lab_overdue", f"Overdue: {w['number']}",
               f"{w['case_type']} for {w['clinic_name']} was due {w['due_on']}", f"/staff/lab/works/{w['id']}")
        conn.execute("UPDATE lab_works SET overdue_notified = 1 WHERE id = ?", (w["id"],))
    # Branch cases sent to the lab: a daily summary per lab (no patient details).
    for r in conn.all(f"SELECT c.lab_id, COUNT(*) AS n FROM lab_cases c WHERE c.status IN {open_works} "
                      "AND c.due_on IS NOT NULL AND c.due_on <= ? GROUP BY c.lab_id", (tomorrow,)):
        notify(conn, lab_staff(conn, r["lab_id"]), "lab_cases_due", f"{r['n']} branch lab case(s) due by tomorrow or overdue",
               "Open Lab cases to see them.", "/staff/lab/")
