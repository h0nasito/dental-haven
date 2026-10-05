"""Clinic attendance rules (confirmed by the clinic):

- Late: every minute after the branch opening time counts (grace period setting, default 0). Staff pay loses
  ₱1 per late minute (setting payroll.late_rate_cents; dentists only if payroll.late_applies_dentists).
- 3rd late in a calendar month: the employee gets a warning email (when email is set up) and HR / super admins get an
  in-app notification. Once per employee per month.
- Staff hours (Oct 2026): 8:00 AM to 5:00 PM (settings payroll.staff_start_time / staff_end_time). Staff are late from
  8:01 (no grace period); dentists are late from the branch opening time.
- Overtime: time after 5:00 PM in whole 30-minute blocks (under 30 min = none, 45 min = 30), plus 30 minutes when the staff member took only a 30-minute lunch (ticked at time-out).
  Only for employees marked "Eligible for overtime" (not commission-based staff or dentists). Late minutes and
  overtime are counted separately. Only overtime a supervisor approves is paid, at daily rate / 8 x 1.25 per hour.
"""
from __future__ import annotations

from flask import current_app

from . import settings
from .notices import notify
from .util import hm_to_min, now_str, parse_date


def schedule(conn, rec) -> dict | None:
    """The working hours that apply to this time record: {start, end, ot_eligible, dentist}, or None on a day off.

    Staff use the clinic's staff hours (8:00-17:00). Dentists use the branch's opening hours. A day the branch is closed
    has no schedule (no lates, no overtime; the record is flagged for review instead)."""
    if not rec.get("work_date"):
        return None
    day = parse_date(rec["work_date"])
    hours = conn.one("SELECT * FROM branch_hours WHERE branch_id = ? AND weekday = ?", (rec.get("branch_id"), day.weekday())) \
        if rec.get("branch_id") else None
    if hours and hours["closed"]:
        return None
    emp = conn.one("SELECT e.ot_eligible, u.role FROM employees e LEFT JOIN users u ON u.id = e.user_id WHERE e.id = ?",
                   (rec.get("employee_id"),)) if rec.get("employee_id") else None
    dentist = bool(emp and emp["role"] == "dentist")
    if dentist:
        if not hours:
            return None
        start, end = hours["open_time"], hours["close_time"]
    else:
        start = settings.get("payroll.staff_start_time", conn) or "08:00"
        end = settings.get("payroll.staff_end_time", conn) or "17:00"
    # Dentists are paid by commission and never earn overtime.
    return {"start": start, "end": end, "dentist": dentist, "ot_eligible": bool(emp and emp["ot_eligible"] and not dentist)}


def day_metrics(conn, rec) -> tuple[int, int]:
    """(late minutes, overtime minutes) for a time record."""
    sch = schedule(conn, rec)
    if not sch:
        return 0, 0
    grace = int(settings.get("payroll.grace_minutes", conn) or 0)
    late = ot = 0
    if rec.get("time_in"):
        late = max(0, hm_to_min(rec["time_in"]) - hm_to_min(sch["start"]) - grace)
    if sch["ot_eligible"] and rec.get("time_out") and rec.get("time_in") and hm_to_min(rec["time_out"]) > hm_to_min(rec["time_in"]):
        ot = max(0, hm_to_min(rec["time_out"]) - hm_to_min(sch["end"]))
        block = int(settings.get("payroll.ot_block_minutes", conn) or 0)
        if block > 1:
            ot = ot // block * block   # minimum one block (30 min), then whole blocks: 25 -> 0, 45 -> 30, 70 -> 60
        if rec.get("short_lunch"):
            ot += int(settings.get("payroll.short_lunch_minutes", conn) or 0)
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
