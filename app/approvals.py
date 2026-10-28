"""Requests waiting for HR / admin approval, and the morning email that lists them.

What needs approval: leave forms, reimbursements, field work (time in outside the clinic), overtime, and payroll
summaries submitted for approval. The bell notifications go out when each request is made; this module also sends
each approver ONE email in the morning listing what is still waiting for them (only when something is waiting).

The email has the type of request, the staff member's name and a link. No reasons, amounts or dates: those are seen
after signing in. Each person can turn the email off in Profile settings; a super admin can turn it off for everyone
(System settings → Approval reminder emails). Nothing is sent from the demo site or while testing.
"""
from __future__ import annotations

import os
from datetime import timedelta

from . import settings
from .permissions import load_user_permissions
from .util import now, now_str, today

OT_DAYS = 62   # overtime older than this isn't listed (it's past the payroll cutoffs)


def _perms(conn, u) -> set[str]:
    return load_user_permissions(conn, u["id"], u["access_role"] or u["role"])


def _branches(conn, u) -> list[int]:
    if u["role"] == "super_admin":
        return [r["id"] for r in conn.all("SELECT id FROM branches WHERE active = 1")]
    return [r["branch_id"] for r in conn.all("SELECT branch_id FROM user_branches WHERE user_id = ?", (u["id"],))]


def approvers(conn, perm: str, branch_id: int | None) -> list[int]:
    """Active users who may approve `perm` for this branch: super admins, and users with the permission assigned to the
    branch (any branch when the request has none)."""
    out = []
    for u in conn.all("SELECT id, role, access_role FROM users WHERE active = 1"):
        if u["role"] == "super_admin":
            out.append(u["id"])
        elif (not branch_id or conn.one("SELECT 1 AS x FROM user_branches WHERE user_id = ? AND branch_id = ?", (u["id"], branch_id))) \
                and perm in _perms(conn, u):
            out.append(u["id"])
    return out


def _names(rows, limit=8) -> str:
    names = list(dict.fromkeys(r["name"] for r in rows))
    shown = ", ".join(names[:limit])
    return shown + (f" and {len(names) - limit} more" if len(names) > limit else "")


def pending_for(conn, u) -> list[dict]:
    """What's waiting for this user to approve: [{label, count, names, path}]. Never their own requests."""
    perms = _perms(conn, u)
    ids = _branches(conn, u)
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    me = conn.one("SELECT id FROM employees WHERE user_id = ?", (u["id"],))
    me_id = me["id"] if me else 0
    out = []

    def add(label, rows, path):
        if rows:
            out.append({"label": label, "count": len(rows), "names": _names(rows), "path": path})

    if "leave.approve" in perms:
        add("Leave forms", conn.all(
            "SELECT e.full_name AS name FROM leave_requests r JOIN employees e ON e.id = r.employee_id WHERE r.status = 'pending' "
            f"AND (r.branch_id IN ({marks}) OR r.branch_id IS NULL) AND r.employee_id != ? ORDER BY r.created_at", [*ids, me_id]),
            "/staff/leave/?show=pending")
    if "reimburse.approve" in perms:
        add("Reimbursements", conn.all(
            "SELECT e.full_name AS name FROM reimbursements r JOIN employees e ON e.id = r.employee_id WHERE r.status = 'pending' "
            f"AND (r.branch_id IN ({marks}) OR r.branch_id IS NULL) AND r.employee_id != ? ORDER BY r.created_at", [*ids, me_id]),
            "/staff/reimbursements/")
    if "attendance.manage" in perms:
        add("Field work (time in outside the clinic)", conn.all(
            "SELECT e.full_name AS name FROM time_records t JOIN employees e ON e.id = t.employee_id WHERE t.field_status = 'pending' "
            f"AND t.branch_id IN ({marks}) AND t.employee_id != ? ORDER BY t.work_date", [*ids, me_id]),
            "/staff/clock/log?flag=field")
    if "overtime.approve" in perms:
        add("Overtime", conn.all(
            "SELECT e.full_name AS name FROM time_records t JOIN employees e ON e.id = t.employee_id WHERE t.ot_minutes > 0 "
            f"AND t.ot_approved_by IS NULL AND t.work_date >= ? AND t.branch_id IN ({marks}) AND t.employee_id != ? ORDER BY t.work_date",
            [(today() - timedelta(days=OT_DAYS)).isoformat(), *ids, me_id]),
            "/staff/attendance?status=ot")
    if "payroll.approve" in perms:
        rows = conn.all("SELECT id, name FROM payroll_periods WHERE status = 'submitted' AND (submitted_by IS NULL OR submitted_by != ?) "
                        f"AND (branch_id IN ({marks}) OR branch_id IS NULL) ORDER BY start_date", [u["id"], *ids])
        add("Payroll summaries", rows, f"/staff/payroll/{rows[0]['id']}" if len(rows) == 1 else "/staff/payroll")
    return out


def compose(u, sections, base: str) -> tuple[str, str]:
    total = sum(s["count"] for s in sections)
    subject = f"{total} request{'s' if total != 1 else ''} waiting for your approval · Dental Haven"
    lines = [f"Hi {u['name']},", "", "These are waiting for your approval in the Dental Haven system:", ""]
    for s in sections:
        lines.append(f"• {s['label']} ({s['count']}): {s['names']}")
        if base:
            lines.append(f"  Open: {base}{s['path']}")
        lines.append("")
    if not base:
        lines += ["Sign in to the staff system to review them.", ""]
    lines += ["—", "Automatic morning reminder from the Dental Haven clinic system. You get it only on days when something is",
              "waiting. To stop these emails, turn off \"Email me approval reminders\" in Profile settings."]
    return subject, "\n".join(lines)


def send_digests(conn, day: str) -> dict:
    """Email each approver what's waiting for them. Returns counts by status."""
    from flask import current_app
    from . import dentist_mail
    from .daily_report import _mail_config
    counts: dict[str, int] = {}
    demo = current_app.config.get("APP_ENV") == "demo" or current_app.config.get("TESTING")
    c = None if demo else _mail_config(conn)
    base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    for u in conn.all("SELECT * FROM users WHERE active = 1 AND notify_approvals = 1 AND email != '' ORDER BY id"):
        if conn.one("SELECT 1 AS x FROM approval_emails WHERE user_id = ? AND sent_day = ? AND status IN ('sent', 'demo')", (u["id"], day)):
            continue
        sections = pending_for(conn, u)
        if not sections:
            continue
        status, error = "sent", ""
        if demo:
            status = "demo"
        elif not c:
            status = "not_set_up"
        else:
            try:
                subject, body = compose(u, sections, base)
                dentist_mail.send_email(u["email"], subject, body, c)
            except Exception as exc:  # noqa: BLE001 - note the failure (no email text), keep going
                status, error = "failed", f"{type(exc).__name__}: {str(exc)[:160]}"
                current_app.logger.warning("Approval reminder to user %s failed: %s", u["id"], type(exc).__name__)
        conn.insert("approval_emails", {"user_id": u["id"], "sent_day": day, "items": sum(s["count"] for s in sections),
                                        "status": status, "error": error, "created_at": now_str()})
        counts[status] = counts.get(status, 0) + 1
    return counts


def run(conn) -> bool:
    """Called often by the background worker: sends the morning reminders once a day, at or after the set time."""
    if not settings.get("approvals.email_enabled", conn):
        return False
    t = now()
    if t.strftime("%H:%M") < (settings.get("approvals.email_time", conn) or "08:00"):
        return False
    day = t.date().isoformat()
    with conn.transaction(immediate=True):   # check and mark together, so two web workers never both send
        if settings.get("approvals.email_last_day", conn) == day:
            return False
        settings.put("approvals.email_last_day", day, None, conn)
    send_digests(conn, day)
    return True


def overtime_detected(conn, rec, old_ot: int, new_ot: int) -> None:
    """Bell notification for approvers when a recent time record gets overtime that nobody has approved yet."""
    from .notices import notify
    if old_ot or not new_ot or rec["ot_approved_by"]:
        return
    if rec["work_date"] < (today() - timedelta(days=3)).isoformat():
        return   # old records (e.g. an import) don't notify
    emp = conn.one("SELECT full_name, user_id FROM employees WHERE id = ?", (rec["employee_id"],))
    if not emp:
        return
    notify(conn, approvers(conn, "overtime.approve", rec["branch_id"]), "overtime", f"Overtime to approve: {emp['full_name']}",
           f"{new_ot} minutes on {rec['work_date']}", "/staff/attendance?status=ot", exclude=emp["user_id"])
