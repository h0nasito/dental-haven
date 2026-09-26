"""Attendance exception detection and draft payroll summaries.

IMPORTANT: The clinic's pay rules (overtime, holidays, night differential, commissions,
associate dentist percentage splits, statutory deductions) have NOT been provided. This
module only aggregates attendance and, for daily/hourly rates, shows an *unconfirmed
estimate* (rate x days or hours). Nothing here pays anyone or produces final payroll.
"""
from __future__ import annotations

from datetime import datetime

from . import settings
from .util import hm_to_min, parse_date

BASIS_LABELS = {"monthly": "Monthly salary", "daily": "Daily rate", "hourly": "Hourly rate",
                "percentage": "Percentage of production", "per_case": "Per case / procedure", "unset": "Not set"}


def evaluate_record(conn, rec: dict) -> tuple[str, str]:
    """Return (status, note) for a time record, flagging exceptions for review."""
    if rec.get("status") in ("corrected", "excused"):
        return rec["status"], rec.get("exception_note", "")
    issues = []
    if not rec.get("time_in"):
        issues.append("missing time-in")
    if not rec.get("time_out"):
        issues.append("missing time-out")
    day = parse_date(rec["work_date"])
    if rec.get("time_in") and rec.get("time_out"):
        if hm_to_min(rec["time_out"]) <= hm_to_min(rec["time_in"]):
            issues.append("time-out before time-in")
        hours = conn.one("SELECT * FROM branch_hours WHERE branch_id = ? AND weekday = ?", (rec["branch_id"], day.weekday()))
        grace = int(settings.get("payroll.grace_minutes", conn) or 0)
        if hours and not hours["closed"]:
            late = hm_to_min(rec["time_in"]) - hm_to_min(hours["open_time"]) - grace
            if late > 0:
                issues.append(f"late {late} min vs branch opening")
            early = hm_to_min(hours["close_time"]) - hm_to_min(rec["time_out"])
            if early > 0:
                issues.append(f"left {early} min before closing")
        elif hours and hours["closed"]:
            issues.append("worked on a day the branch is closed")
    return ("exception", "; ".join(issues)) if issues else ("ok", "")


def worked_minutes(rec) -> int:
    if not rec["time_in"] or not rec["time_out"]:
        return 0
    return max(0, hm_to_min(rec["time_out"]) - hm_to_min(rec["time_in"]))


def current_compensation(conn, employee_id: int, as_of: str):
    return conn.one("SELECT * FROM compensation WHERE employee_id = ? AND effective_from <= ? ORDER BY effective_from DESC, id DESC LIMIT 1",
                    (employee_id, as_of))


def build_lines(conn, period) -> list[dict]:
    where = "e.active = 1"
    params: list = []
    if period["branch_id"]:
        where += " AND e.primary_branch_id = ?"
        params.append(period["branch_id"])
    employees = conn.all(f"SELECT e.* FROM employees e WHERE {where} ORDER BY e.full_name", params)
    lines = []
    for e in employees:
        recs = conn.all("SELECT * FROM time_records WHERE employee_id = ? AND work_date BETWEEN ? AND ?",
                        (e["id"], period["start_date"], period["end_date"]))
        days = sum(1 for r in recs if r["time_in"] and r["time_out"] and r["status"] in ("ok", "corrected", "exception"))
        minutes = sum(worked_minutes(r) for r in recs if r["status"] != "excused")
        late = 0
        undertime = 0
        for r in recs:
            if r["status"] == "exception" and r["exception_note"]:
                for part in r["exception_note"].split("; "):
                    if part.startswith("late "):
                        late += int(part.split(" ")[1])
                    if part.startswith("left "):
                        undertime += int(part.split(" ")[1])
        open_exc = sum(1 for r in recs if r["status"] == "exception")
        comp = current_compensation(conn, e["id"], period["end_date"])
        basis = comp["basis"] if comp else "unset"
        rate = comp["rate_cents"] if comp else None
        estimate = None
        if rate is not None and basis == "daily":
            estimate = days * rate
        elif rate is not None and basis == "hourly":
            estimate = round(minutes / 60 * rate)
        lines.append({"employee_id": e["id"], "days_present": days, "minutes_worked": minutes, "late_minutes": late,
                      "undertime_minutes": undertime, "open_exceptions": open_exc, "basis": basis, "rate_cents": rate,
                      "percentage_bp": comp["percentage_bp"] if comp else None, "estimate_cents": estimate})
    return lines


def parse_time(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(value.upper(), fmt).strftime("%H:%M")
        except ValueError:
            continue
    return None
