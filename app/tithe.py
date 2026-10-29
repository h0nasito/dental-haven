"""Monthly tithe: a share (default 10%) of the month's net profit, emailed to the daily collection report recipients.

Net profit is the Monthly business report's: collections minus expenses (daily expenses and monthly bills, lab fees on
bills paid) minus payroll (salaries and wages, dentist commissions, approved payroll runs ending in the month). A month
that ran at a loss has no tithe. The email for a month goes out once, on report.tithe_day of the next month (default the
5th, so the month's payroll is usually approved by then), at the daily report time. No patient names.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import settings
from .util import now, now_str, peso


def prev_month(d: date) -> date:
    return (d.replace(day=1) - timedelta(days=1)).replace(day=1)


def rate(conn) -> int:
    v = settings.get("report.tithe_percent", conn)
    return v if isinstance(v, int) and 0 < v <= 100 else 10


def build(conn, month: date) -> dict:
    from .business_report import figures, month_bounds
    start, end = month_bounds(month)
    branches = [dict(b) for b in conn.all("SELECT * FROM branches WHERE active = 1 ORDER BY sort_order")]
    per = []
    for b in branches:
        f = figures(conn, [b], start, end)
        if f["gross"] or f["expenses"] or f["payroll"]:
            per.append({"name": b["name"], "gross": f["gross"], "expenses": f["expenses"], "payroll": f["payroll"], "net": f["net"]})
    tot = figures(conn, branches, start, end)
    pct = rate(conn)
    payroll_open = conn.scalar("SELECT COUNT(*) FROM payroll_periods WHERE status != 'approved' AND end_date BETWEEN ? AND ?",
                               (start.isoformat(), end.isoformat())) or 0
    return {"month": start, "label": start.strftime("%B %Y"), "branches": per, "gross": tot["gross"], "expenses": tot["expenses"],
            "payroll": tot["payroll"], "net": tot["net"], "percent": pct, "tithe": max(0, round(tot["net"] * pct / 100)),
            "drafts": tot.get("drafts") or 0, "payroll_open": payroll_open}


def as_text(t: dict) -> str:
    lines = [f"Tithe for {t['label']}", "",
             f"Net profit: {peso(t['net'])}",
             f"Tithe ({t['percent']}% of net profit): {peso(t['tithe'])}", "",
             f"  Collections   {peso(t['gross'])}",
             f"  Expenses      -{peso(t['expenses'])}   (daily expenses, monthly bills, lab fees)",
             f"  Payroll       -{peso(t['payroll'])}   (salaries, dentist commissions, approved payroll)",
             f"  Net profit    {peso(t['net'])}"]
    if t["net"] <= 0:
        lines += ["", "The month ran at a loss, so there is no tithe."]
    if len(t["branches"]) > 1:
        lines += ["", "By branch (net profit):"] + [f"  {b['name']}: {peso(b['net'])}" for b in t["branches"]]
    notes = []
    if t["payroll_open"]:
        notes.append(f"{t['payroll_open']} payroll run(s) for this month are not approved yet, so payroll may be higher and the tithe lower.")
    if t["drafts"]:
        notes.append(f"Expenses include {peso(t['drafts'])} not yet posted (still drafts).")
    if notes:
        lines += ["", "Please note:"] + [f"  - {n}" for n in notes]
    lines += ["", "Details: Reports > Monthly business report.", "", "Dental Haven (automatic email)"]
    return "\n".join(lines)


def send(conn, month: date, to: list[str] | None = None) -> tuple[int, str]:
    from flask import current_app
    from . import daily_report, dentist_mail
    to = to if to is not None else daily_report.recipients(conn)
    if not to:
        return 0, "No recipients set (System settings → Daily collection report)."
    if current_app.config.get("APP_ENV") == "demo" or current_app.config.get("TESTING"):
        return 0, "Not sent: the demo site never sends emails."
    c = daily_report._mail_config(conn)
    if not c:
        return 0, "Email isn't set up on the server."
    t = build(conn, month)
    body = as_text(t)
    sent, errors = 0, []
    for addr in to:
        try:
            dentist_mail.send_email(addr, f"Monthly tithe · {t['label']} · {peso(t['tithe'])}", body, c)
            sent += 1
        except Exception as exc:  # noqa: BLE001 - report each address, keep going
            errors.append(f"{addr}: {exc}"[:200])
    conn.insert("report_sends", {"report_day": f"tithe {month.strftime('%Y-%m')}", "recipients": ", ".join(to), "sent": sent,
                                 "error": "; ".join(errors)[:1000], "created_at": now_str()})
    return sent, (f"Sent to {sent} of {len(to)}." + (" Problems: " + "; ".join(errors) if errors else ""))


def run(conn) -> bool:
    """Called often by the background worker: sends last month's tithe once, on the set day, at the daily report time."""
    if not settings.get("report.tithe_enabled", conn):
        return False
    t = now()
    day = settings.get("report.tithe_day", conn) or 5
    at = settings.get("report.daily_time", conn) or "23:00"
    if t.day < min(max(int(day), 1), 28) or t.strftime("%H:%M") < at:
        return False
    month = prev_month(t.date())
    key = month.strftime("%Y-%m")
    with conn.transaction(immediate=True):   # check and mark together, so two web workers never both send
        last = settings.get("report.tithe_last_month", conn)
        if last == key:
            return False
        settings.put("report.tithe_last_month", key, None, conn)
        if last is None and t.day > min(max(int(day), 1), 28):
            return False                     # just turned on after this month's send day: start with next month
    send(conn, month)
    return True
