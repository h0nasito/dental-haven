"""Scheduling rules: durations, operating hours, dentist schedules, conflict checks, availability."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import settings
from .util import fmt_dt, hm_to_min, min_to_hm, now

ACTIVE_STATUSES = ("requested", "confirmed", "checked_in")
STATUSES = {
    "requested": "Requested",
    "confirmed": "Confirmed",
    "checked_in": "Checked in",
    "completed": "Completed",
    "cancelled": "Cancelled",
    "no_show": "No-show",
}
# Allowed status transitions (staff workflow)
TRANSITIONS = {
    "requested": {"confirmed", "cancelled"},
    "confirmed": {"checked_in", "cancelled", "no_show"},
    "checked_in": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
    "no_show": set(),
}
SOURCES = {
    "staff": "Staff entry",
    "phone": "Phone call",
    "walk_in": "Walk-in",
    "website": "Website request",
    "facebook": "Facebook / Messenger",
    "referral": "Referral",
    "other": "Other",
}


def service_duration(conn, service_id: int, branch_id: int | None = None, dentist_id: int | None = None) -> int:
    rows = conn.all("SELECT branch_id, dentist_id, minutes FROM service_durations WHERE service_id = ?", (service_id,))
    best, best_score = None, -1
    for r in rows:
        if r["branch_id"] not in (None, branch_id) or r["dentist_id"] not in (None, dentist_id):
            continue
        score = (2 if r["dentist_id"] else 0) + (1 if r["branch_id"] else 0)
        if score > best_score:
            best, best_score = r["minutes"], score
    if best is not None:
        return int(best)
    svc = conn.one("SELECT default_duration_min FROM services WHERE id = ?", (service_id,))
    return int(svc["default_duration_min"]) if svc else 30


def branch_hours(conn, branch_id: int, day: date):
    row = conn.one("SELECT * FROM branch_hours WHERE branch_id = ? AND weekday = ?", (branch_id, day.weekday()))
    if not row or row["closed"]:
        return None
    return row["open_time"], row["close_time"]


def dentist_windows(conn, dentist_id: int, branch_id: int, day: date):
    """Scheduled windows for a dentist at a branch on a day. None = no schedule configured at all
    (treated as available during branch hours); [] = configured but not working that day."""
    has_any = conn.scalar("SELECT COUNT(*) FROM dentist_schedules WHERE dentist_id = ?", (dentist_id,))
    if not has_any:
        return None
    rows = conn.all(
        "SELECT start_time, end_time FROM dentist_schedules WHERE dentist_id = ? AND branch_id = ? AND weekday = ? "
        "ORDER BY start_time",
        (dentist_id, branch_id, day.weekday()),
    )
    return [(r["start_time"], r["end_time"]) for r in rows]


def find_conflicts(conn, start: str, end: str, dentist_id=None, resource_id=None, exclude_id=None):
    """Active appointments overlapping [start, end) for the same dentist (any branch) or resource."""
    clauses, params = [], []
    if dentist_id:
        clauses.append("a.dentist_id = ?")
        params.append(dentist_id)
    if resource_id:
        clauses.append("a.resource_id = ?")
        params.append(resource_id)
    if not clauses:
        return []
    marks = ",".join("?" for _ in ACTIVE_STATUSES)
    sql = (
        "SELECT a.*, u.name AS dentist_name, r.name AS resource_name FROM appointments a "
        "LEFT JOIN users u ON u.id = a.dentist_id LEFT JOIN resources r ON r.id = a.resource_id "
        f"WHERE a.status IN ({marks}) AND a.start_at < ? AND a.end_at > ? AND ({' OR '.join(clauses)})"
    )
    args = [*ACTIVE_STATUSES, end, start, *params]
    if exclude_id:
        sql += " AND a.id != ?"
        args.append(exclude_id)
    return conn.all(sql, args)


def free_resource(conn, branch_id: int, start: str, end: str, exclude_id=None):
    """First active resource at the branch without an overlapping active appointment.
    Returns (resource_id, has_resources)."""
    resources = conn.all("SELECT id FROM resources WHERE branch_id = ? AND active = 1 ORDER BY id", (branch_id,))
    if not resources:
        return None, False
    for r in resources:
        if not find_conflicts(conn, start, end, resource_id=r["id"], exclude_id=exclude_id):
            return r["id"], True
    return None, True


def validate_slot(conn, *, branch_id: int, start: datetime, end: datetime, dentist_id=None, resource_id=None,
                  exclude_id=None, allow_past=False) -> list[str]:
    errors = []
    if end <= start:
        errors.append("End time must be after start time.")
        return errors
    if start.date() != end.date():
        errors.append("Appointments must start and end on the same day.")
    if not allow_past and start < now() - timedelta(minutes=5):
        errors.append("That time is in the past.")
    hours = branch_hours(conn, branch_id, start.date())
    s_min, e_min = start.hour * 60 + start.minute, end.hour * 60 + end.minute
    if hours is None:
        errors.append("The branch is closed on that day.")
    elif s_min < hm_to_min(hours[0]) or e_min > hm_to_min(hours[1]):
        errors.append(f"Outside branch hours ({hours[0]}–{hours[1]}).")
    if dentist_id:
        windows = dentist_windows(conn, dentist_id, branch_id, start.date())
        if windows is not None and not any(hm_to_min(a) <= s_min and e_min <= hm_to_min(b) for a, b in windows):
            errors.append("The dentist is not scheduled at this branch at that time.")
    s, e = fmt_dt(start), fmt_dt(end)
    for c in find_conflicts(conn, s, e, dentist_id=dentist_id, resource_id=resource_id, exclude_id=exclude_id):
        who = []
        if dentist_id and c["dentist_id"] == dentist_id:
            who.append(f"dentist already booked {c['start_at'][11:]}–{c['end_at'][11:]}")
        if resource_id and c["resource_id"] == resource_id:
            who.append(f"{c['resource_name'] or 'room'} in use {c['start_at'][11:]}–{c['end_at'][11:]}")
        errors.append("Conflict: " + "; ".join(who) + ".")
    return errors


def available_slots(conn, *, branch_id: int, service_id: int, day: date, dentist_id=None) -> list[str]:
    """Start times (HH:MM) at which a request could be accommodated. Used by the public form.
    A pending request does not hold the slot; staff confirm against live availability."""
    hours = branch_hours(conn, branch_id, day)
    if hours is None:
        return []
    step = int(settings.get("booking.slot_step_min", conn) or 30)
    notice = timedelta(hours=int(settings.get("booking.min_notice_hours", conn) or 0))
    earliest = now() + notice
    if dentist_id:
        dentists = [dentist_id]
    else:
        dentists = [r["id"] for r in conn.all(
            "SELECT u.id FROM users u JOIN user_branches ub ON ub.user_id = u.id "
            "WHERE u.role = 'dentist' AND u.active = 1 AND ub.branch_id = ?", (branch_id,))]
    slots = []
    open_m, close_m = hm_to_min(hours[0]), hm_to_min(hours[1])
    t = open_m
    while t < close_m:
        start = datetime.combine(day, datetime.min.time()) + timedelta(minutes=t)
        t += step
        if start < earliest:
            continue
        ok = False
        for d in dentists or [None]:
            minutes = service_duration(conn, service_id, branch_id, d)
            end = start + timedelta(minutes=minutes)
            res_id, has_res = free_resource(conn, branch_id, fmt_dt(start), fmt_dt(end))
            if has_res and res_id is None:
                continue
            if not validate_slot(conn, branch_id=branch_id, start=start, end=end, dentist_id=d, resource_id=res_id):
                ok = True
                break
        if ok:
            slots.append(min_to_hm(start.hour * 60 + start.minute))
    return slots


def ensure_assignment(conn, patient_id: int, dentist_id, by_user=None):
    """Dentists see clinical records of patients they are assigned to. Booking with a dentist assigns them."""
    if not dentist_id:
        return
    if not conn.one("SELECT 1 AS x FROM patient_assignments WHERE patient_id = ? AND dentist_id = ?",
                    (patient_id, dentist_id)):
        from .util import now_str
        conn.execute(
            "INSERT INTO patient_assignments (patient_id, dentist_id, created_at, created_by) VALUES (?, ?, ?, ?)",
            (patient_id, dentist_id, now_str(), by_user),
        )
