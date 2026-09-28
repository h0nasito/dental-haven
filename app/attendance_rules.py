"""Clinic attendance rules (confirmed by the clinic):

- Late: every minute after the branch opening time counts (grace period setting, default 0). Staff pay loses
  ₱1 per late minute (setting payroll.late_rate_cents; dentists only if payroll.late_applies_dentists).
- 3rd late in a calendar month: the employee gets a warning email (when email is set up) and HR / super admins get an
  in-app notification. Once per employee per month.
- Overtime: minutes after the branch closing time are detected, but only overtime a supervisor approves is paid.
"""
from __future__ import annotations

from flask import current_app

from . import settings
from .notices import notify
from .util import hm_to_min, now_str, parse_date


def day_metrics(conn, rec) -> tuple[int, int]:
    """(late minutes, overtime minutes) for a time record, against the branch's hours that weekday."""
    if not rec.get("work_date"):
        return 0, 0
    day = parse_date(rec["work_date"])
    hours = conn.one("SELECT * FROM branch_hours WHERE branch_id = ? AND weekday = ?", (rec["branch_id"], day.weekday()))
    if not hours or hours["closed"]:
        return 0, 0
    grace = int(settings.get("payroll.grace_minutes", conn) or 0)
    late = ot = 0
    if rec.get("time_in"):
        late = max(0, hm_to_min(rec["time_in"]) - hm_to_min(hours["open_time"]) - grace)
    if rec.get("time_out") and rec.get("time_in") and hm_to_min(rec["time_out"]) > hm_to_min(rec["time_in"]):
        ot = max(0, hm_to_min(rec["time_out"]) - hm_to_min(hours["close_time"]))
    return late, ot


def refresh_record(conn, rec_id: int):
    """Store late/overtime minutes on a time record and check the monthly late warning."""
    rec = conn.one("SELECT * FROM time_records WHERE id = ?", (rec_id,))
    if not rec:
        return
    late, ot = day_metrics(conn, dict(rec))
    if rec["status"] == "excused":
        late = 0
    conn.execute("UPDATE time_records SET late_minutes = ?, ot_minutes = ?, ot_approved_minutes = MIN(ot_approved_minutes, ?) WHERE id = ?",
                 (late, ot, ot, rec_id))
    if late:
        check_late_warning(conn, rec["employee_id"], rec["work_date"][:7])


def check_late_warning(conn, employee_id: int, month: str):
    count = conn.scalar("SELECT COUNT(*) FROM time_records WHERE employee_id = ? AND substr(work_date, 1, 7) = ? AND late_minutes > 0 "
                        "AND status != 'excused'", (employee_id, month)) or 0
    if count < 3 or conn.one("SELECT id FROM late_warnings WHERE employee_id = ? AND month = ?", (employee_id, month)):
        return
    emp = conn.one("SELECT e.*, u.email, u.id AS uid, b.slug AS branch_slug, b.name AS branch FROM employees e LEFT JOIN users u ON u.id = e.user_id "
                   "LEFT JOIN branches b ON b.id = e.primary_branch_id WHERE e.id = ?", (employee_id,))
    status = _email_warning(emp, month, count)
    conn.insert("late_warnings", {"employee_id": employee_id, "month": month, "late_count": count, "email_status": status, "created_at": now_str()})
    admins = [r["id"] for r in conn.all("SELECT id FROM users WHERE active = 1 AND (role = 'super_admin' OR access_role = 'hr')")]
    notify(conn, admins, "late_warning", f"Late warning: {emp['full_name']}", f"{count} late arrivals in {month}. Email: {status}.",
           f"/staff/attendance?employee={employee_id}")
    if emp["uid"]:
        notify(conn, [emp["uid"]], "late_warning", "Warning: 3 late arrivals this month",
               "Please be on time. Each late minute is deducted at ₱1 per minute.", "/staff/attendance")


def _email_warning(emp, month: str, count: int) -> str:
    from . import dentist_mail
    if not emp["email"]:
        return "no email address"
    if current_app.config.get("APP_ENV") == "demo" or current_app.config.get("TESTING"):
        return "not sent (demo/test)"
    c = dentist_mail.config(emp["branch_slug"], emp["branch"] or "")
    if not c:
        return "not sent (email not set up)"
    body = (f"Hi {emp['full_name'].split(' ')[0]},\n\n"
            f"This is a formal reminder from Dental Haven management: our records show {count} late arrivals in {month}.\n"
            "Please report on time. As per clinic policy, late minutes are deducted from pay at ₱1 per minute, and repeated "
            "lateness may lead to further action.\n\n"
            "If a record is wrong, please talk to your supervisor or HR so it can be corrected.\n\n"
            "Dental Haven Management")
    try:
        dentist_mail.send_email(emp["email"], "Dental Haven: attendance warning (late arrivals)", body, c)
        return "sent"
    except Exception:  # noqa: BLE001 - never block attendance on email problems
        return "failed"
