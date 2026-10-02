"""Attendance exception detection and draft payroll summaries.

Clinic-confirmed rules: cutoffs 1-15 and 16-end of month; late = ₱1 per minute (staff); overtime paid only when a
supervisor approves it, at daily rate / 8 x 1.25 per hour; regular holiday worked = double pay, special non-working
day worked = +30%; unworked regular holiday = 1 day (setting). Night differential and statutory deductions
(SSS, PhilHealth, Pag-IBIG, tax) are NOT computed. This module aggregates attendance and shows *estimates*: rate x days or hours
for staff, and for dentists daily rate x days present + commission (clinic-confirmed basis: amount billed
for each completed procedure, less its share of the invoice discount and the lab fee, x commission %).
Nothing here pays anyone or produces final payroll.
"""
from __future__ import annotations

from datetime import datetime

from . import settings
from .util import hm_to_min, now_str, parse_date

BASIS_LABELS = {"monthly": "Monthly salary", "daily": "Daily rate", "hourly": "Hourly rate",
                "percentage": "Percentage of production", "per_case": "Per case / procedure", "unset": "Not set",
                "daily_commission": "Daily rate + commission"}


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


def dentist_rates(conn, employee_id: int, as_of: str):
    return conn.one("SELECT * FROM dentist_pay_rates WHERE employee_id = ? AND effective_from <= ? ORDER BY effective_from DESC, id DESC LIMIT 1",
                    (employee_id, as_of))


def commission_items(conn, user_id: int, start: str, end: str, branch_id=None, default_bp: int = 0, service_bp: dict | None = None):
    """Procedure lines a dentist completed in the period, on issued invoices, with the commission for each.

    base = line amount - its share of the invoice-level discount - lab fee (never below zero); commission = base x rate.
    """
    service_bp = service_bp or {}
    where, args = ["ii.dentist_id = ?", "i.status = 'issued'", "ii.done_on BETWEEN ? AND ?"], [user_id, start, end]
    if branch_id:
        where.append("i.branch_id = ?")
        args.append(branch_id)
    rows = conn.all("SELECT ii.*, i.number AS invoice_number, i.branch_id, i.discount_cents AS inv_discount, i.subtotal_cents AS inv_subtotal, "
                    "p.chart_no, b.name AS branch, s.name AS service FROM invoice_items ii JOIN invoices i ON i.id = ii.invoice_id "
                    "JOIN patients p ON p.id = i.patient_id JOIN branches b ON b.id = i.branch_id LEFT JOIN services s ON s.id = ii.service_id "
                    f"WHERE {' AND '.join(where)} ORDER BY ii.done_on, ii.id", args)
    out = []
    for r in rows:
        r = dict(r)
        share = round(r["inv_discount"] * r["amount_cents"] / r["inv_subtotal"]) if r["inv_discount"] and r["inv_subtotal"] else 0
        r["discount_share_cents"] = share
        r["base_cents"] = max(0, r["amount_cents"] - share - (r["lab_fee_cents"] or 0))
        mode = r.get("commission_mode") or "auto"
        if mode == "amount" and r.get("commission_cents") is not None:
            r["rate_bp"] = None                      # fixed amount typed on the bill line
        else:
            r["rate_bp"] = r["commission_bp"] if mode == "percent" and r.get("commission_bp") is not None \
                else service_bp.get(r["service_id"], default_bp)
            r["commission_cents"] = round(r["base_cents"] * r["rate_bp"] / 10000)
            if mode != "percent":
                mode = "auto"
        r["commission_mode"] = mode
        out.append(r)
    return out


def per_procedure(conn) -> bool:
    """True when dentist commission comes from bill lines (date done); False when the cashier records it per payment."""
    return settings.get("payroll.dentist_commission_basis", conn) == "procedure"


def manual_commissions(conn, employee_id: int, start: str, end: str):
    """Manual dentist commission entries dated inside the period (e.g. per ortho adjustment payment)."""
    return conn.all("SELECT c.*, i.number AS invoice_number, p.chart_no, u.name AS by_name FROM dentist_commissions c "
                    "LEFT JOIN invoices i ON i.id = c.invoice_id LEFT JOIN patients p ON p.id = i.patient_id "
                    "LEFT JOIN users u ON u.id = c.created_by WHERE c.employee_id = ? AND c.status = 'valid' "
                    "AND c.earned_on BETWEEN ? AND ? ORDER BY c.earned_on, c.id", (employee_id, start, end))


OT_MULTIPLIER = 1.25          # clinic rule: hourly OT rate = daily rate / 8 x 1.25
HOLIDAY_WORKED = {"regular": 2.0, "special": 1.3}   # regular holiday worked = double pay; special non-working = +30%


def staff_daily_pay(conn, recs, rate_cents: int, start: str, end: str) -> dict:
    """Daily-rate staff: basic pay, holiday pay, approved overtime and late deduction for the period."""
    holidays = {h["day"]: h["kind"] for h in conn.all("SELECT day, kind FROM holidays WHERE day BETWEEN ? AND ?", (start, end))}
    basic = holiday = 0
    worked_days = set()
    for r in recs:
        if r["time_in"] and r["time_out"] and r["status"] in ("ok", "corrected", "exception"):
            worked_days.add(r["work_date"])
            basic += rate_cents
            kind = holidays.get(r["work_date"])
            if kind:
                holiday += round(rate_cents * (HOLIDAY_WORKED[kind] - 1))
    if settings.get("payroll.pay_unworked_regular_holiday", conn):
        holiday += sum(rate_cents for d, k in holidays.items() if k == "regular" and d not in worked_days)
    ot_minutes = sum(r["ot_approved_minutes"] or 0 for r in recs if r["status"] != "excused")
    ot_pay = round(ot_minutes / 60 * rate_cents / 8 * OT_MULTIPLIER)
    late_minutes = sum(r["late_minutes"] or 0 for r in recs if r["status"] != "excused")
    late = late_minutes * int(settings.get("payroll.late_peso_per_minute", conn) or 0) * 100
    return {"basic_pay_cents": basic, "holiday_pay_cents": holiday, "ot_minutes": ot_minutes, "ot_pay_cents": ot_pay,
            "late_deduction_cents": late, "late_minutes": late_minutes, "estimate_cents": basic + holiday + ot_pay - late}


def build_lines(conn, period) -> list[dict]:
    where = "e.active = 1"
    params: list = []
    if period["branch_id"]:
        where += " AND e.primary_branch_id = ?"
        params.append(period["branch_id"])
    employees = conn.all(f"SELECT e.* FROM employees e WHERE {where} ORDER BY e.full_name", params)
    lines = []
    for e in employees:
        all_recs = conn.all("SELECT * FROM time_records WHERE employee_id = ? AND work_date BETWEEN ? AND ?",
                            (e["id"], period["start_date"], period["end_date"]))
        # Field work counts only once approved; pending or declined field days are left out.
        recs = [r for r in all_recs if r["field_status"] in (None, "approved")]
        days = sum(1 for r in recs if r["time_in"] and r["time_out"] and r["status"] in ("ok", "corrected", "exception"))
        minutes = sum(worked_minutes(r) for r in recs if r["status"] != "excused")
        late = sum(r["late_minutes"] or 0 for r in recs if r["status"] != "excused")
        undertime = 0
        for r in recs:
            if r["status"] == "exception" and r["exception_note"]:
                for part in r["exception_note"].split("; "):
                    if part.startswith("left "):
                        undertime += int(part.split(" ")[1])
        open_exc = sum(1 for r in all_recs if r["status"] == "exception")
        user = conn.one("SELECT id, role FROM users WHERE id = ?", (e["user_id"],)) if e["user_id"] else None
        if user and user["role"] == "dentist":
            rates = dentist_rates(conn, e["id"], period["end_date"])
            svc = {r["service_id"]: r["commission_bp"] for r in conn.all("SELECT * FROM dentist_service_rates WHERE employee_id = ?", (e["id"],))}
            items = commission_items(conn, user["id"], period["start_date"], period["end_date"], period["branch_id"],
                                     rates["commission_bp"] if rates else 0, svc) if per_procedure(conn) else []
            manual = manual_commissions(conn, e["id"], period["start_date"], period["end_date"])
            daily_pay = days * rates["daily_rate_cents"] if rates else None
            commission = (sum(i["commission_cents"] for i in items) + sum(m["amount_cents"] for m in manual)) if rates else None
            late_min = sum(r["late_minutes"] or 0 for r in recs if r["status"] != "excused")
            late_ded = late_min * int(settings.get("payroll.late_peso_per_minute", conn) or 0) * 100 \
                if settings.get("payroll.late_applies_dentists", conn) else 0
            lines.append({"employee_id": e["id"], "days_present": days, "minutes_worked": minutes, "late_minutes": late,
                          "undertime_minutes": undertime, "open_exceptions": open_exc, "kind": "dentist",
                          "basis": "daily_commission" if rates else "unset", "rate_cents": rates["daily_rate_cents"] if rates else None,
                          "percentage_bp": rates["commission_bp"] if rates else None, "daily_pay_cents": daily_pay,
                          "commission_cents": commission, "commission_base_cents": sum(i["base_cents"] for i in items),
                          "commission_items": len(items) + len(manual), "late_deduction_cents": late_ded if rates else None,
                          "estimate_cents": (daily_pay + commission - late_ded) if rates else None})
            continue
        is_tech = "technician" in (e["position"] or "").lower() or bool(user and conn.one("SELECT 1 AS x FROM users WHERE id = ? AND access_role = 'technician'", (user["id"],)))
        comp = current_compensation(conn, e["id"], period["end_date"])
        basis = comp["basis"] if comp else "unset"
        rate = comp["rate_cents"] if comp else None
        estimate = None
        extra = {}
        if rate is not None and basis == "daily":
            extra = staff_daily_pay(conn, recs, rate, period["start_date"], period["end_date"])
            estimate = extra.pop("estimate_cents")
            late = extra.pop("late_minutes")
        elif rate is not None and basis == "hourly":
            estimate = round(minutes / 60 * rate)
        lines.append({"employee_id": e["id"], "days_present": days, "minutes_worked": minutes, "late_minutes": late,
                      "undertime_minutes": undertime, "open_exceptions": open_exc, "basis": basis, "rate_cents": rate,
                      "percentage_bp": comp["percentage_bp"] if comp else None, "estimate_cents": estimate, "kind": "staff", **extra})
        if is_tech:
            from .lab_commission import for_period
            items = for_period(conn, e["id"], period["start_date"], period["end_date"])
            comm = sum(i["amount_cents"] for i in items)
            lines[-1].update({"commission_cents": comm, "commission_items": len(items)})
            if lines[-1]["estimate_cents"] is not None:
                lines[-1]["estimate_cents"] += comm
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


def add_manual_commission(conn, dentist_user_id: int | None, employee_id: int | None, earned_on, base_cents, rate_bp, amount_cents,
                          by_user_id: int, invoice_id=None, payment_id=None, description: str = ""):
    """Record a manual dentist commission. Give either amount_cents, or base_cents + rate_bp (amount = base x rate).
    Returns (id, error)."""
    if not employee_id and dentist_user_id:
        emp = conn.one("SELECT e.id FROM employees e JOIN users u ON u.id = e.user_id WHERE u.id = ? AND u.role = 'dentist'", (dentist_user_id,))
        if not emp:
            return None, "This dentist has no employee record yet (Staff & payroll → Employees), so commission can't be recorded."
        employee_id = emp["id"]
    if not employee_id:
        return None, "Choose the dentist."
    if amount_cents is None:
        if base_cents is None or rate_bp is None:
            return None, "Enter the commission amount, or the amount paid and the commission %."
        amount_cents = round(base_cents * rate_bp / 10000)
    if amount_cents < 0:
        return None, "The commission can't be negative."
    cid = conn.insert("dentist_commissions", {"employee_id": employee_id, "earned_on": earned_on.isoformat(), "invoice_id": invoice_id,
                                              "payment_id": payment_id, "description": description[:200], "base_cents": base_cents,
                                              "rate_bp": rate_bp, "amount_cents": amount_cents, "created_by": by_user_id,
                                              "created_at": now_str()})
    return cid, None
